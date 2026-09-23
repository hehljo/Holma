#!/usr/bin/env python3
"""Regression test for concurrent SQLite application startup."""

import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing


BACKEND_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))


class StartupConcurrencyTests(unittest.TestCase):
    def test_parallel_app_factories_do_not_race_schema_creation(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = os.path.join(temp_dir, 'backupgenie.db')
            environment = os.environ.copy()
            environment.update({
                'SECRET_KEY': 'parallel-startup-test-secret-key-123456789',
                'DATABASE_URL': f'sqlite:///{database_path}',
                'APP_INIT_LOCK_PATH': os.path.join(temp_dir, 'init.lock'),
                'DEFAULT_ADMIN_PASSWORD': 'Parallel-Startup-Test-123!',
                'SOURCES_CONFIG_PATH': os.path.join(temp_dir, 'sources.json'),
                'NOTIFICATION_CONFIG_PATH': os.path.join(
                    temp_dir, 'notifications.json'
                ),
                'LOG_FILE': os.path.join(temp_dir, 'app.log'),
            })
            command = [
                sys.executable,
                '-W',
                'error',
                '-c',
                'from app import create_app; create_app()',
            ]
            processes = [
                subprocess.Popen(
                    command,
                    cwd=BACKEND_ROOT,
                    env=environment,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                for _ in range(4)
            ]

            failures = []
            for process in processes:
                stdout, stderr = process.communicate(timeout=30)
                if process.returncode != 0:
                    failures.append(
                        f'exit={process.returncode}\nstdout={stdout}\nstderr={stderr}'
                    )
            self.assertFalse(failures, '\n\n'.join(failures))

            with closing(sqlite3.connect(database_path)) as connection:
                tables = {
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    )
                }
                users = connection.execute('SELECT COUNT(*) FROM users').fetchone()[0]

            self.assertTrue(
                {'backups', 'backup_source_results', 'settings', 'users'} <= tables
            )
            self.assertEqual(users, 1)


if __name__ == '__main__':
    unittest.main()
