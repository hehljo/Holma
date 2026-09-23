"""Durable backup job reservation and coordination.

Job metadata is stored in the existing backup tables.  A small file lock
serializes reservations across the API, scheduler and worker processes so two
requests cannot reserve the same source at the same time.
"""
from contextlib import contextmanager
import fcntl
import logging
import os
import uuid

from app import db
from app.backup.paths import validate_source_id
from app.config import Config
from app.models.backup import Backup, BackupSourceResult, Setting
from app.time_utils import utc_now_naive

logger = logging.getLogger(__name__)

ACTIVE_BACKUP_STATUSES = ('pending', 'running', 'cancelling')
ACTIVE_SOURCE_STATUSES = ('pending', 'running')


class JobValidationError(ValueError):
    """The requested source selection or execution options are invalid."""

    def __init__(self, message, *, source_ids=None, status_code=400):
        super().__init__(message)
        self.source_ids = sorted(source_ids or [])
        self.status_code = status_code


class JobConflictError(RuntimeError):
    """At least one requested source is already reserved by an active job."""

    def __init__(self, source_ids):
        super().__init__('Backup already running for these sources')
        self.source_ids = sorted(source_ids)


@contextmanager
def job_lock():
    """Serialize job state transitions across all local processes."""
    lock_path = Config.JOB_LOCK_PATH
    parent = os.path.dirname(lock_path)
    if parent:
        os.makedirs(parent, exist_ok=True)

    with open(lock_path, 'a+', encoding='utf-8') as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def configured_parallel_limit():
    """Return the effective, bounded runtime parallelism setting."""
    raw = Setting.get('max_parallel_tasks', Config.MAX_PARALLEL_TASKS)
    try:
        return min(10, max(1, int(raw)))
    except (TypeError, ValueError):
        return min(10, max(1, int(Config.MAX_PARALLEL_TASKS)))


def effective_parallelism(requested=None):
    """Validate a request and cap it at the configured runtime maximum."""
    maximum = configured_parallel_limit()
    if requested is None:
        return maximum
    if isinstance(requested, bool):
        raise JobValidationError('parallel must be an integer between 1 and 10')
    try:
        value = int(requested)
    except (TypeError, ValueError) as exc:
        raise JobValidationError(
            'parallel must be an integer between 1 and 10'
        ) from exc
    if value < 1 or value > 10:
        raise JobValidationError('parallel must be an integer between 1 and 10')
    return min(value, maximum)


def active_source_ids():
    """Return source IDs reserved by active or queued backup jobs."""
    rows = (
        db.session.query(BackupSourceResult.source_id)
        .join(Backup, BackupSourceResult.backup_id == Backup.id)
        .filter(
            Backup.status.in_(ACTIVE_BACKUP_STATUSES),
            BackupSourceResult.status.in_(ACTIVE_SOURCE_STATUSES),
        )
        .all()
    )
    return {row[0] for row in rows}


def _select_sources(all_sources, requested_source_ids):
    """Validate and resolve a request against the current source config."""
    known = {source.get('id'): source for source in all_sources if source.get('id')}

    if requested_source_ids is None:
        selected = [source for source in all_sources if source.get('enabled', True)]
    else:
        if not isinstance(requested_source_ids, list):
            raise JobValidationError('sources must be an array')

        requested = []
        seen = set()
        for source_id in requested_source_ids:
            try:
                source_id = validate_source_id(source_id)
            except (TypeError, ValueError) as exc:
                raise JobValidationError(str(exc)) from exc
            if source_id not in seen:
                requested.append(source_id)
                seen.add(source_id)

        unknown = [source_id for source_id in requested if source_id not in known]
        if unknown:
            raise JobValidationError(
                'Unknown sources', source_ids=unknown, status_code=404
            )
        disabled = [
            source_id for source_id in requested
            if not known[source_id].get('enabled', True)
        ]
        if disabled:
            raise JobValidationError(
                'Sources are disabled', source_ids=disabled, status_code=409
            )
        selected = [known[source_id] for source_id in requested]

    if not selected:
        raise JobValidationError('No enabled sources selected', status_code=409)

    for source in selected:
        try:
            validate_source_id(source.get('id'))
        except (TypeError, ValueError) as exc:
            raise JobValidationError(
                f"Invalid configured source: {source.get('name', '?')}"
            ) from exc

    return selected


def reserve_backup(
    all_sources,
    requested_source_ids=None,
    trigger_type='manual',
    parallel=None,
):
    """Atomically reserve sources and create a durable pending backup job."""
    selected = _select_sources(all_sources, requested_source_ids)
    selected_ids = [source['id'] for source in selected]

    with job_lock():
        try:
            db.session.expire_all()
            busy = active_source_ids() & set(selected_ids)
            if busy:
                raise JobConflictError(busy)

            backup = Backup(
                backup_id=str(uuid.uuid4()),
                status='pending',
                trigger_type=trigger_type,
                sources_count=len(selected),
            )
            db.session.add(backup)
            db.session.flush()

            for source in selected:
                db.session.add(BackupSourceResult(
                    backup_id=backup.id,
                    source_id=source['id'],
                    source_name=source.get('name') or source['id'],
                    source_type=source.get('type') or 'unknown',
                    status='pending',
                ))

            if parallel is not None:
                db.session.add(Setting(
                    key=f'job.parallel.{backup.backup_id}',
                    value=str(parallel),
                ))

            db.session.commit()
            return backup, selected
        except Exception:
            db.session.rollback()
            raise


def job_parallelism(backup_id):
    """Load a queued job's requested parallelism, bounded by current config."""
    setting = Setting.query.filter_by(key=f'job.parallel.{backup_id}').first()
    requested = setting.value if setting else None
    return effective_parallelism(requested)


def clear_job_runtime_settings(backup_id):
    """Remove temporary execution metadata after a job is terminal."""
    Setting.query.filter_by(key=f'job.parallel.{backup_id}').delete()
    db.session.commit()


def cancel_backup_job(backup_id):
    """Cancel a queued job or request graceful cancellation of a running job."""
    with job_lock():
        backup = Backup.query.filter_by(backup_id=backup_id).first()
        if not backup:
            return None, 'not_found'

        if backup.status == 'pending':
            now = utc_now_naive()
            backup.status = 'cancelled'
            backup.completed_at = now
            backup.duration = int((now - backup.started_at).total_seconds())
            for result in backup.source_results:
                if result.status == 'pending':
                    result.status = 'cancelled'
                    result.completed_at = now
                    result.duration = int((now - result.started_at).total_seconds())
                    result.error_message = 'Cancelled before execution'
            Setting.query.filter_by(key=f'job.parallel.{backup.backup_id}').delete()
            db.session.commit()
            return backup, 'cancelled'

        if backup.status == 'running':
            backup.status = 'cancelling'
            db.session.commit()
            return backup, 'cancelling'

        if backup.status == 'cancelling':
            return backup, 'cancelling'

        return backup, 'not_running'


def claim_next_backup():
    """Claim the oldest queued job for the dedicated worker."""
    with job_lock():
        while True:
            backup = (
                Backup.query.filter_by(status='pending')
                .order_by(Backup.started_at.asc(), Backup.id.asc())
                .first()
            )
            if not backup:
                return None

            if not backup.source_results:
                now = utc_now_naive()
                backup.status = 'failed'
                backup.completed_at = now
                backup.duration = int((now - backup.started_at).total_seconds())
                backup.error_message = 'Pending job has no reserved sources'
                db.session.commit()
                logger.error('Rejected backup %s without reserved sources', backup.backup_id)
                continue

            backup.status = 'running'
            db.session.commit()
            return backup.backup_id


def recover_interrupted_backups():
    """Finalize jobs left active by a previous worker process."""
    recovered = 0
    with job_lock():
        backups = Backup.query.filter(
            Backup.status.in_(('running', 'cancelling'))
        ).all()
        now = utc_now_naive()

        for backup in backups:
            was_cancelling = backup.status == 'cancelling'
            backup.status = 'cancelled' if was_cancelling else 'failed'
            backup.completed_at = now
            backup.duration = int((now - backup.started_at).total_seconds())
            backup.error_message = (
                'Cancellation completed after worker restart'
                if was_cancelling else 'Backup interrupted by worker restart'
            )
            for result in backup.source_results:
                if result.status in ACTIVE_SOURCE_STATUSES:
                    result.status = 'cancelled' if was_cancelling else 'failed'
                    result.completed_at = now
                    result.duration = int((now - result.started_at).total_seconds())
                    result.error_message = backup.error_message
            Setting.query.filter_by(key=f'job.parallel.{backup.backup_id}').delete()
            recovered += 1

        if recovered:
            db.session.commit()
    return recovered
