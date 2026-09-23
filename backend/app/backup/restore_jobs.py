"""Durable, encrypted coordination for Supabase restore jobs."""

from contextlib import contextmanager
import fcntl
import json
import logging
import os
import tempfile
import uuid

from app.config import Config
from app.crypto import decrypt_value, encrypt_value
from app.time_utils import utc_iso_z

logger = logging.getLogger(__name__)

ACTIVE_RESTORE_STATUSES = ('queued', 'running')
TERMINAL_RESTORE_STATUSES = ('completed', 'partial', 'failed')


class RestoreJobError(RuntimeError):
    """A persisted restore job is invalid or unavailable."""


def validate_restore_id(restore_id):
    """Return a canonical UUID or reject path-like identifiers."""
    try:
        parsed = uuid.UUID(str(restore_id))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError('Invalid restore id') from exc
    canonical = str(parsed)
    if str(restore_id) != canonical:
        raise ValueError('Invalid restore id')
    return canonical


def _job_directory():
    directory = os.path.realpath(Config.RESTORE_JOB_PATH)
    if directory == os.path.dirname(directory):
        raise RestoreJobError('Restore job directory must not be a filesystem root')
    created = not os.path.exists(directory)
    os.makedirs(directory, mode=0o700, exist_ok=True)
    if created:
        os.chmod(directory, 0o700)
    elif os.stat(directory).st_mode & 0o077:
        raise RestoreJobError('Restore job directory permissions are too broad')
    return directory


def _job_path(restore_id):
    restore_id = validate_restore_id(restore_id)
    return os.path.join(_job_directory(), f'{restore_id}.json')


@contextmanager
def restore_job_lock():
    """Serialize claims and status updates across local processes."""
    lock_path = Config.RESTORE_JOB_LOCK_PATH
    parent = os.path.dirname(lock_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(lock_path, 'a+', encoding='utf-8') as lock_file:
        os.chmod(lock_path, 0o600)
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _write_job(job):
    """Atomically persist one private job file with restrictive permissions."""
    directory = _job_directory()
    target = _job_path(job['restore_id'])
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode='w',
            encoding='utf-8',
            dir=directory,
            prefix='.restore-',
            suffix='.tmp',
            delete=False,
        ) as temp_file:
            temp_path = temp_file.name
            json.dump(job, temp_file, separators=(',', ':'))
            temp_file.flush()
            os.fsync(temp_file.fileno())
        os.chmod(temp_path, 0o600)
        os.replace(temp_path, target)
    except Exception:
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)
        raise


def _read_job(restore_id):
    path = _job_path(restore_id)
    try:
        with open(path, encoding='utf-8') as job_file:
            job = json.load(job_file)
    except FileNotFoundError:
        return None
    except (OSError, json.JSONDecodeError) as exc:
        raise RestoreJobError('Restore job state is unreadable') from exc
    if not isinstance(job, dict) or job.get('restore_id') != restore_id:
        raise RestoreJobError('Restore job state is invalid')
    return job


def _public_status(job):
    """Remove the encrypted execution payload from API-visible state."""
    return {key: value for key, value in job.items() if key != 'payload'}


def enqueue_restore(payload):
    """Persist a queued restore with its credentials encrypted at rest."""
    if not isinstance(payload, dict):
        raise ValueError('Restore payload must be an object')
    restore_id = str(uuid.uuid4())
    now = utc_iso_z()
    encrypted_payload = encrypt_value(json.dumps(payload, separators=(',', ':')))
    job = {
        'restore_id': restore_id,
        'status': 'queued',
        'created_at': now,
        'updated_at': now,
        'logs': '',
        'payload': encrypted_payload,
    }
    with restore_job_lock():
        _write_job(job)
    return _public_status(job)


def read_restore_status(restore_id):
    """Read public persisted status for one restore."""
    restore_id = validate_restore_id(restore_id)
    with restore_job_lock():
        job = _read_job(restore_id)
    return _public_status(job) if job else None


def update_restore_status(restore_id, **changes):
    """Atomically update a restore job without exposing its payload."""
    restore_id = validate_restore_id(restore_id)
    forbidden = {'restore_id', 'created_at'} & set(changes)
    if forbidden:
        raise ValueError('Immutable restore job field')
    with restore_job_lock():
        job = _read_job(restore_id)
        if not job:
            raise RestoreJobError('Restore job not found')
        job.update(changes)
        job['updated_at'] = utc_iso_z()
        _write_job(job)
    return _public_status(job)


def claim_next_restore():
    """Claim the oldest queued restore and decrypt its private payload."""
    with restore_job_lock():
        candidates = []
        for name in os.listdir(_job_directory()):
            if not name.endswith('.json'):
                continue
            try:
                restore_id = validate_restore_id(name[:-5])
                job = _read_job(restore_id)
            except (ValueError, RestoreJobError):
                continue
            if job and job.get('status') == 'queued':
                candidates.append(job)

        if not candidates:
            return None, None

        job = min(
            candidates,
            key=lambda item: (item.get('created_at', ''), item['restore_id']),
        )
        try:
            plaintext = decrypt_value(job.get('payload', ''))
            payload = json.loads(plaintext) if plaintext else None
            if not isinstance(payload, dict):
                raise ValueError('invalid payload')
        except (ValueError, json.JSONDecodeError):
            job.update({
                'status': 'failed',
                'error': 'Encrypted restore payload is unavailable',
                'payload': '',
                'updated_at': utc_iso_z(),
                'completed_at': utc_iso_z(),
            })
            _write_job(job)
            return None, None

        job.update({
            'status': 'running',
            'started_at': utc_iso_z(),
            'updated_at': utc_iso_z(),
        })
        _write_job(job)
        return job['restore_id'], payload


def recover_interrupted_restores():
    """Fail interrupted running restores; queued jobs remain queued."""
    recovered = 0
    with restore_job_lock():
        for name in os.listdir(_job_directory()):
            if not name.endswith('.json'):
                continue
            try:
                restore_id = validate_restore_id(name[:-5])
                job = _read_job(restore_id)
            except (ValueError, RestoreJobError):
                continue
            if job and job.get('status') == 'running':
                now = utc_iso_z()
                job.update({
                    'status': 'failed',
                    'error': 'Restore interrupted by worker restart',
                    'payload': '',
                    'updated_at': now,
                    'completed_at': now,
                })
                _write_job(job)
                recovered += 1
    return recovered


def execute_restore_job(restore_id, payload):
    """Execute one claimed restore and persist live logs plus terminal state."""
    from app.backup.paths import ensure_path_within
    from app.backup.restore import SupabaseRestore

    restorer = SupabaseRestore()
    restorer._status_callback = lambda logs: update_restore_status(
        restore_id, logs=logs
    )
    try:
        backup_path = ensure_path_within(
            Config.BACKUP_BASE_PATH, payload['backup_path']
        )
        if not os.path.exists(backup_path):
            raise FileNotFoundError('Restore backup no longer exists')
        result = restorer.restore(
            backup_path, payload.get('target_config', {})
        )
        return update_restore_status(
            restore_id,
            status=result.get('status', 'completed'),
            steps_total=result.get('steps_total', 0),
            steps_completed=result.get('steps_completed', 0),
            errors=result.get('errors', []),
            logs=result.get('logs', ''),
            completed_at=utc_iso_z(),
            payload='',
        )
    except Exception as exc:
        logger.exception('Restore %s failed', restore_id)
        return update_restore_status(
            restore_id,
            status='failed',
            error=str(exc),
            logs=restorer.get_logs(),
            completed_at=utc_iso_z(),
            payload='',
        )
