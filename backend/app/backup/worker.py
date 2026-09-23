"""Dedicated process for executing durable backup jobs."""
import logging
import os
import signal
import threading

from app import create_app
from app.backup.executor import BackupExecutor
from app.backup.jobs import (
    claim_next_backup,
    clear_job_runtime_settings,
    job_parallelism,
    recover_interrupted_backups,
)
from app.backup.restore_jobs import (
    claim_next_restore,
    execute_restore_job,
    recover_interrupted_restores,
)

logger = logging.getLogger(__name__)


class BackupWorker:
    def __init__(self, app):
        self.app = app
        self._stop = threading.Event()
        self.poll_seconds = max(1, int(os.environ.get('JOB_POLL_SECONDS', '2')))

    def stop(self):
        self._stop.set()

    def run(self):
        with self.app.app_context():
            recovered = recover_interrupted_backups()
            if recovered:
                logger.warning('Finalized %d interrupted backup job(s)', recovered)
            recovered_restores = recover_interrupted_restores()
            if recovered_restores:
                logger.warning(
                    'Finalized %d interrupted restore job(s)', recovered_restores
                )

        logger.info('Backup worker started (poll every %ss)', self.poll_seconds)
        while not self._stop.is_set():
            restore_id, restore_payload = claim_next_restore()
            if restore_id:
                logger.info('Executing queued restore %s', restore_id)
                with self.app.app_context():
                    execute_restore_job(restore_id, restore_payload)
                continue

            with self.app.app_context():
                backup_id = claim_next_backup()
                parallel = job_parallelism(backup_id) if backup_id else None

            if not backup_id:
                self._stop.wait(self.poll_seconds)
                continue

            logger.info('Executing queued backup %s', backup_id)
            try:
                with self.app.app_context():
                    executor = BackupExecutor(backup_id, app=self.app)
                executor.execute(parallel=parallel)
            finally:
                with self.app.app_context():
                    clear_job_runtime_settings(backup_id)

        logger.info('Backup worker stopped')


def main():
    logging.basicConfig(
        level=os.environ.get('LOG_LEVEL', 'INFO'),
        format='%(asctime)s %(levelname)s [worker] %(message)s',
    )
    app = create_app()
    worker = BackupWorker(app)

    def handle_signal(signum, frame):
        logger.info('Received signal %s, stopping after the current source', signum)
        worker.stop()

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)
    worker.run()


if __name__ == '__main__':
    main()
