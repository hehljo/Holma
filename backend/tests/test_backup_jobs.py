#!/usr/bin/env python3
"""Regression checks for durable backup job coordination."""

import os
import sys
import tempfile
import unittest
from unittest.mock import patch

from flask import Flask


BACKEND_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

from app import db
from app.backup.base import BackupHandler
from app.backup.executor import BackupExecutor
from app.backup.sources.smb import SMBBackup
from app.backup.jobs import (
    JobConflictError,
    JobValidationError,
    active_source_ids,
    cancel_backup_job,
    claim_next_backup,
    effective_parallelism,
    recover_interrupted_backups,
    reserve_backup,
)
from app.config import Config
from app.models.backup import Backup, BackupSourceResult, Setting


class SuccessfulHandler(BackupHandler):
    def backup(self):
        return {'files_synced': 1, 'size_synced': 12, 'logs': 'ok'}


class BackupJobTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.app = Flask('backup-job-test')
        self.app.config.update(
            SQLALCHEMY_DATABASE_URI='sqlite:///:memory:',
            SQLALCHEMY_TRACK_MODIFICATIONS=False,
        )
        db.init_app(self.app)
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        self.lock_patch = patch.object(
            Config,
            'JOB_LOCK_PATH',
            os.path.join(self.temp_dir.name, 'jobs.lock'),
        )
        self.backup_path_patch = patch.object(
            Config, 'BACKUP_BASE_PATH', self.temp_dir.name
        )
        self.lock_patch.start()
        self.backup_path_patch.start()
        self.sources = [
            {'id': 'source-a', 'name': 'A', 'type': 'test', 'enabled': True},
            {'id': 'source-b', 'name': 'B', 'type': 'test', 'enabled': True},
        ]

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        db.engine.dispose()
        self.context.pop()
        self.backup_path_patch.stop()
        self.lock_patch.stop()
        self.temp_dir.cleanup()

    def test_reservation_blocks_same_source_before_execution(self):
        backup, selected = reserve_backup(
            self.sources, ['source-a'], parallel=1
        )

        self.assertEqual(backup.status, 'pending')
        self.assertEqual([source['id'] for source in selected], ['source-a'])
        self.assertEqual(active_source_ids(), {'source-a'})
        self.assertEqual(BackupSourceResult.query.one().status, 'pending')

        with self.assertRaises(JobConflictError):
            reserve_backup(self.sources, ['source-a'], parallel=1)

    def test_disjoint_sources_can_be_queued(self):
        reserve_backup(self.sources, ['source-a'], parallel=1)
        reserve_backup(self.sources, ['source-b'], parallel=1)
        self.assertEqual(Backup.query.filter_by(status='pending').count(), 2)

    def test_unknown_and_disabled_sources_are_rejected(self):
        with self.assertRaisesRegex(JobValidationError, 'Unknown sources'):
            reserve_backup(self.sources, ['missing'], parallel=1)

        disabled = self.sources + [
            {'id': 'disabled', 'name': 'Disabled', 'type': 'test', 'enabled': False}
        ]
        with self.assertRaisesRegex(JobValidationError, 'Sources are disabled'):
            reserve_backup(disabled, ['disabled'], parallel=1)

    def test_queued_stop_is_terminal_and_releases_source(self):
        backup, _ = reserve_backup(self.sources, ['source-a'], parallel=1)
        stopped, state = cancel_backup_job(backup.backup_id)

        self.assertEqual(state, 'cancelled')
        self.assertEqual(stopped.status, 'cancelled')
        self.assertEqual(stopped.source_results[0].status, 'cancelled')
        self.assertEqual(active_source_ids(), set())
        self.assertIsNone(
            Setting.query.filter_by(key=f'job.parallel.{backup.backup_id}').first()
        )

    def test_running_stop_is_visible_across_processes(self):
        backup, _ = reserve_backup(self.sources, ['source-a'], parallel=1)
        self.assertEqual(claim_next_backup(), backup.backup_id)

        _, state = cancel_backup_job(backup.backup_id)
        executor = BackupExecutor(
            backup.backup_id, enable_notifications=False, app=self.app
        )

        self.assertEqual(state, 'cancelling')
        self.assertTrue(executor._stop_is_requested())

    def test_worker_restart_finalizes_running_but_preserves_queue(self):
        first, _ = reserve_backup(self.sources, ['source-a'], parallel=1)
        second, _ = reserve_backup(self.sources, ['source-b'], parallel=1)
        self.assertEqual(claim_next_backup(), first.backup_id)

        self.assertEqual(recover_interrupted_backups(), 1)
        self.assertEqual(
            Backup.query.filter_by(backup_id=first.backup_id).one().status,
            'failed',
        )
        self.assertEqual(
            Backup.query.filter_by(backup_id=second.backup_id).one().status,
            'pending',
        )

    def test_executor_uses_reserved_rows_and_finishes_job(self):
        backup, _ = reserve_backup(self.sources, ['source-a'], parallel=1)
        claim_next_backup()
        executor = BackupExecutor(
            backup.backup_id, enable_notifications=False, app=self.app
        )
        executor.backup_base_path = self.temp_dir.name
        executor.handlers = {'test': SuccessfulHandler}
        executor.load_sources = lambda: self.sources

        executor.execute(parallel=1)

        db.session.expire_all()
        stored = Backup.query.filter_by(backup_id=backup.backup_id).one()
        self.assertEqual(stored.status, 'completed')
        self.assertEqual(stored.total_size, 12)
        self.assertEqual(len(stored.source_results), 1)
        self.assertEqual(stored.source_results[0].status, 'completed')

    def test_parallel_request_is_validated_and_capped(self):
        db.session.add(Setting(key='max_parallel_tasks', value='2'))
        db.session.commit()

        self.assertEqual(effective_parallelism(8), 2)
        with self.assertRaisesRegex(ValueError, 'parallel must be an integer'):
            effective_parallelism(0)

    def test_nas_ui_type_uses_smb_handler(self):
        executor = BackupExecutor('mapping-test', enable_notifications=False)
        self.assertIs(executor.handlers['nas'], SMBBackup)


if __name__ == '__main__':
    unittest.main(verbosity=2)
