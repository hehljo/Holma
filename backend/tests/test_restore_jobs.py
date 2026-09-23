#!/usr/bin/env python3
"""Regression checks for durable encrypted restore coordination."""

import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch


BACKEND_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

from app.backup.restore_jobs import (
    claim_next_restore,
    enqueue_restore,
    execute_restore_job,
    read_restore_status,
    recover_interrupted_restores,
    validate_restore_id,
)
from app.backup.restore import SupabaseRestore
from app.config import Config
import app.crypto as crypto


class RestoreJobTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.patches = [
            patch.object(Config, 'SECRET_KEY', 'restore-test-secret-key-123456789012345'),
            patch.object(Config, 'RESTORE_JOB_PATH', self.temp_dir.name),
            patch.object(Config, 'BACKUP_BASE_PATH', self.temp_dir.name),
            patch.object(
                Config,
                'RESTORE_JOB_LOCK_PATH',
                os.path.join(self.temp_dir.name, 'restore.lock'),
            ),
        ]
        for active_patch in self.patches:
            active_patch.start()
        crypto._fernet = None

    def tearDown(self):
        crypto._fernet = None
        for active_patch in reversed(self.patches):
            active_patch.stop()
        self.temp_dir.cleanup()

    @staticmethod
    def _payload():
        backup_path = os.path.join(Config.BACKUP_BASE_PATH, 'supabase_test')
        return {
            'backup_path': backup_path,
            'target_config': {
                'target_connection_string': (
                    'postgresql://tester:not-a-real-secret@db.example/app'
                ),
                'restore_storage': False,
            },
        }

    def test_job_payload_is_encrypted_and_status_survives_claim(self):
        queued = enqueue_restore(self._payload())
        restore_id = queued['restore_id']
        path = os.path.join(self.temp_dir.name, f'{restore_id}.json')

        with open(path, encoding='utf-8') as job_file:
            raw = job_file.read()
        self.assertNotIn('not-a-real-secret', raw)
        self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)
        self.assertNotIn('payload', read_restore_status(restore_id))

        claimed_id, payload = claim_next_restore()
        self.assertEqual(claimed_id, restore_id)
        self.assertEqual(payload, self._payload())
        self.assertEqual(read_restore_status(restore_id)['status'], 'running')

    def test_interrupted_running_job_fails_without_retrying(self):
        first = enqueue_restore(self._payload())
        second = enqueue_restore(self._payload())
        claimed_id, _ = claim_next_restore()
        self.assertEqual(claimed_id, first['restore_id'])

        self.assertEqual(recover_interrupted_restores(), 1)
        interrupted = read_restore_status(first['restore_id'])
        self.assertEqual(interrupted['status'], 'failed')
        self.assertIn('worker restart', interrupted['error'])

        next_id, _ = claim_next_restore()
        self.assertEqual(next_id, second['restore_id'])

    def test_execution_persists_logs_and_purges_private_payload(self):
        os.makedirs(self._payload()['backup_path'])
        queued = enqueue_restore(self._payload())
        restore_id, payload = claim_next_restore()

        def fake_restore(restorer, backup_path, target_config):
            restorer.log('Restore test running')
            return {
                'status': 'completed',
                'steps_total': 1,
                'steps_completed': 1,
                'errors': [],
                'logs': restorer.get_logs(),
            }

        with patch.object(SupabaseRestore, 'restore', fake_restore):
            completed = execute_restore_job(restore_id, payload)

        self.assertEqual(completed['status'], 'completed')
        self.assertIn('Restore test running', completed['logs'])
        path = os.path.join(self.temp_dir.name, f'{restore_id}.json')
        with open(path, encoding='utf-8') as job_file:
            raw = json.load(job_file)
        self.assertEqual(raw['payload'], '')

    def test_restore_id_rejects_path_input(self):
        with self.assertRaises(ValueError):
            validate_restore_id('../../restore')


if __name__ == '__main__':
    unittest.main(verbosity=2)
