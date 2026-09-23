"""
Scheduler loop.

Started as a single process from entrypoint.sh, next to gunicorn. It only
queues durable jobs; the dedicated backup worker executes them.

Every tick it checks which enabled sources are due, then starts one backup run
containing all of them — not one run per source — so a shared 03:00 schedule
does not spawn twenty parallel runs.
"""
from datetime import datetime
import json
import logging
import os
import signal
import threading

from app.scheduler.schedule import (
    describe_schedule,
    get_default_schedule,
    next_run_after,
    resolve_schedule,
)

logger = logging.getLogger(__name__)

# How often the loop wakes up to look for due sources.
TICK_SECONDS = int(os.environ.get('SCHEDULER_TICK_SECONDS', '30'))

# A source due more than this long ago is treated as a missed run and fired
# immediately once (e.g. the container was down overnight), rather than being
# skipped silently until the next occurrence.
CATCHUP_GRACE_SECONDS = int(os.environ.get('SCHEDULER_CATCHUP_SECONDS', '3600'))

LAST_RUN_KEY_PREFIX = 'schedule.last_run.'


class BackupScheduler:
    """Polls source schedules and triggers backups when they come due."""

    def __init__(self, app):
        self.app = app
        self._stop = threading.Event()

    def stop(self):
        self._stop.set()

    def _load_sources(self):
        from app.api.sources import load_sources

        return load_sources()

    def _get_last_run(self, source_id):
        from app.models.backup import Setting

        raw = Setting.get(f'{LAST_RUN_KEY_PREFIX}{source_id}')
        if not raw:
            return None
        try:
            return datetime.fromisoformat(raw)
        except (ValueError, TypeError):
            return None

    def _set_last_run(self, source_id, when):
        from app.models.backup import Setting

        Setting.set(f'{LAST_RUN_KEY_PREFIX}{source_id}', when.isoformat())

    def _due_sources(self, now):
        """Return ids of enabled sources whose next run time has passed."""
        default_schedule = get_default_schedule()
        due = []

        for source in self._load_sources():
            source_id = source.get('id')
            if not source_id:
                continue
            if not source.get('enabled', True):
                continue

            schedule = resolve_schedule(source, default_schedule)
            if not schedule.get('enabled'):
                continue
            if 'cron' not in schedule.get('trigger', ''):
                continue

            last_run = self._get_last_run(source_id)
            if last_run is None:
                # First time we see this source: arm it for its next occurrence
                # instead of firing immediately on container start.
                scheduled = next_run_after(schedule, now)
                if scheduled:
                    self._set_last_run(source_id, now)
                    logger.info(
                        "Armed '%s' (%s), next run %s",
                        source_id, describe_schedule(schedule),
                        scheduled.isoformat(timespec='minutes'),
                    )
                continue

            scheduled = next_run_after(schedule, last_run)
            if scheduled is None:
                continue
            if scheduled > now:
                continue

            overdue = (now - scheduled).total_seconds()
            if overdue > CATCHUP_GRACE_SECONDS:
                logger.info(
                    "Source '%s' was due %s (%.0f min ago, missed while offline), running now",
                    source_id, scheduled.isoformat(timespec='minutes'), overdue / 60,
                )

            due.append(source_id)

        return due

    def _start_backup(self, source_ids, now):
        from app.backup.jobs import configured_parallel_limit, reserve_backup

        parallel = configured_parallel_limit()
        backup, selected = reserve_backup(
            self._load_sources(),
            source_ids,
            trigger_type='scheduled',
            parallel=parallel,
        )

        for source_id in (source['id'] for source in selected):
            self._set_last_run(source_id, now)

        logger.info(
            'Scheduled backup %s queued for %d source(s): %s',
            backup.backup_id, len(selected),
            ', '.join(source['id'] for source in selected),
        )
        return backup.backup_id

    def tick(self):
        """One scheduling pass. Safe to call directly in tests."""
        with self.app.app_context():
            # Local time: users configure "03:00" meaning their wall clock,
            # so set TZ in docker-compose to match your region.
            now = datetime.now()
            due = self._due_sources(now)
            if not due:
                return None

            from app.backup.jobs import JobConflictError, active_source_ids

            busy = active_source_ids() & set(due)
            available = [source_id for source_id in due if source_id not in busy]
            if not available:
                logger.info(
                    'Backup already running, deferring %d scheduled source(s)', len(due)
                )
                return None

            if busy:
                logger.info('Deferring busy scheduled source(s): %s', ', '.join(sorted(busy)))

            try:
                return self._start_backup(available, now)
            except JobConflictError:
                # Another process won the reservation race. Last-run markers
                # remain untouched, so the scheduler retries on the next tick.
                logger.info('Scheduled source reservation raced; retrying next tick')
                return None

    def run(self):
        logger.info('Backup scheduler started (tick every %ss)', TICK_SECONDS)
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception as exc:
                logger.exception('Scheduler tick failed: %s', exc)
            self._stop.wait(TICK_SECONDS)
        logger.info('Backup scheduler stopped')


def main():
    """Process entry point, invoked by entrypoint.sh."""
    logging.basicConfig(
        level=os.environ.get('LOG_LEVEL', 'INFO'),
        format='%(asctime)s %(levelname)s [scheduler] %(message)s',
    )

    from app import create_app

    app = create_app()
    scheduler = BackupScheduler(app)

    def handle_signal(signum, frame):
        logger.info('Received signal %s, shutting down scheduler', signum)
        scheduler.stop()

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    scheduler.run()


if __name__ == '__main__':
    main()
