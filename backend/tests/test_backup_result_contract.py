#!/usr/bin/env python3
"""Regression checks for truthful backup handler results."""

import os
import io
import sys
import tempfile
import unittest
import sqlite3
import tarfile
from contextlib import closing
from types import SimpleNamespace
from unittest.mock import patch


BACKEND_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

from app.backup.base import InvalidBackupResult, normalize_backup_result
from app.backup.base import BackupHandler
from app.backup.executor import BackupExecutor
from app.backup.sources.ftp import FTPBackup, SFTPBackup
from app.backup.sources.rsync_ssh import RsyncSSHBackup
from app.backup.sources.rclone import RcloneBackup
from app.backup.sources.local import LocalBackup
from app.backup.sources.smb import SMBBackup
from app.backup.sources.selfhosted import SelfHostedBackup
from app.backup.sources.database import (
    InfluxDBBackup,
    MongoDBBackup,
    MySQLBackup,
    RedisBackup,
    SQLiteBackup,
)
from app.backup.sources.docker import DockerVolumeBackup
from app.backup.sources.git import GitBackup
from app import db
from app.models.backup import Backup, BackupSourceResult
from flask import Flask


class ResultContractTests(unittest.TestCase):
    def test_nested_source_config_is_flattened_for_every_handler(self):
        handler = LocalBackup(
            {
                'id': 'nested',
                'host': 'old.example',
                'config': {
                    'host': 'new.example',
                    'password': 'not-a-real-secret',
                },
            },
            tempfile.gettempdir(),
        )
        self.assertEqual(handler.source_config['id'], 'nested')
        self.assertEqual(handler.source_config['host'], 'new.example')
        self.assertEqual(
            handler.source_config['password'], 'not-a-real-secret'
        )

    def test_valid_result_is_completed(self):
        result = normalize_backup_result({
            'files_synced': 0,
            'size_synced': 0,
            'logs': 'Empty source checked successfully',
        })
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(result['errors'], [])

    def test_error_without_artifacts_is_failed(self):
        result = normalize_backup_result({
            'files_synced': 0,
            'size_synced': 0,
            'logs': 'ERROR: rsync failed',
        })
        self.assertEqual(result['status'], 'failed')

    def test_error_with_artifacts_is_partial(self):
        result = normalize_backup_result({
            'files_synced': 2,
            'size_synced': 100,
            'logs': 'ERROR backing up third item',
        })
        self.assertEqual(result['status'], 'partial')

    def test_warning_alone_does_not_fake_a_failure(self):
        result = normalize_backup_result({
            'files_synced': 1,
            'size_synced': 5,
            'logs': 'WARNING: optional wiki not found',
        })
        self.assertEqual(result['status'], 'completed')

    def test_invalid_contract_is_rejected(self):
        for result in (
            None,
            {},
            {'files_synced': -1, 'size_synced': 0, 'logs': ''},
            {'files_synced': 0, 'size_synced': '0', 'logs': ''},
        ):
            with self.subTest(result=result):
                with self.assertRaises(InvalidBackupResult):
                    normalize_backup_result(result)


class CommandFailureTests(unittest.TestCase):
    @staticmethod
    def _successful_rsync_result():
        return SimpleNamespace(
            returncode=0,
            stdout='Number of files: 2\nTotal file size: 42 bytes\n',
            stderr='',
        )

    def test_local_rsync_nonzero_raises(self):
        completed = SimpleNamespace(returncode=23, stdout='', stderr='I/O error')
        with tempfile.TemporaryDirectory() as destination:
            handler = LocalBackup({'id': 'local-test', 'path': '/tmp'}, destination)
            with patch('app.backup.sources.local.subprocess.run', return_value=completed):
                with self.assertRaisesRegex(Exception, 'rsync failed'):
                    handler._rsync_path('/tmp', destination)

    def test_smb_rsync_nonzero_raises(self):
        completed = SimpleNamespace(returncode=12, stdout='', stderr='protocol error')
        with tempfile.TemporaryDirectory() as destination:
            handler = SMBBackup({'id': 'smb-test', 'type': 'smb'}, destination)
            with patch('app.backup.sources.smb.subprocess.run', return_value=completed):
                with self.assertRaisesRegex(Exception, 'rsync failed'):
                    handler._rsync_files()

    def test_smb_password_is_only_in_process_environment(self):
        calls = []

        def fake_run(command, **kwargs):
            calls.append((command, kwargs))
            tar_bytes = io.BytesIO()
            with tarfile.open(fileobj=tar_bytes, mode='w') as archive:
                payload = b'kept'
                info = tarfile.TarInfo('file.txt')
                info.size = len(payload)
                archive.addfile(info, io.BytesIO(payload))
            kwargs['stdout'].write(tar_bytes.getvalue())
            return SimpleNamespace(returncode=0, stderr=b'')

        config = {
            'id': 'smb-test',
            'type': 'smb',
            'source': '//diskstation/test',
            'username': 'tester',
            'password': 'not-a-real-secret',
        }
        with tempfile.TemporaryDirectory() as destination:
            with patch('app.backup.sources.smb.subprocess.run', side_effect=fake_run):
                result = SMBBackup(config, destination).backup()

        command, kwargs = calls[0]
        self.assertEqual(result['files_synced'], 1)
        self.assertNotIn('not-a-real-secret', command)
        self.assertEqual(kwargs['env']['PASSWD'], 'not-a-real-secret')

    def test_smb_connection_test_only_lists_the_share(self):
        completed = SimpleNamespace(returncode=0, stderr=b'')
        config = {
            'id': 'smb-test',
            'type': 'nas',
            'source': '//diskstation/test',
            'username': 'tester',
            'password': 'not-a-real-secret',
        }
        with tempfile.TemporaryDirectory() as destination:
            handler = SMBBackup(config, destination)
            with patch(
                'app.backup.sources.smb.subprocess.run', return_value=completed
            ) as run:
                self.assertTrue(handler.test_connection())

        command = run.call_args.args[0]
        kwargs = run.call_args.kwargs
        self.assertEqual(command[-2:], ['-c', 'ls'])
        self.assertNotIn('not-a-real-secret', command)
        self.assertEqual(kwargs['env']['PASSWD'], 'not-a-real-secret')

    def test_rclone_copy_never_syncs_or_exposes_s3_secrets(self):
        completed = SimpleNamespace(
            returncode=0,
            stdout='Transferred: 42 / 42 Bytes\nTransferred: 3\n',
            stderr='',
        )
        config = {
            'id': 's3-test',
            'type': 's3',
            'bucket': 'safe-bucket',
            'path': 'documents',
            'access_key': 'access-id',
            'secret_key': 'not-a-real-secret',
        }
        with tempfile.TemporaryDirectory() as destination:
            handler = RcloneBackup(config, destination)
            with patch(
                'app.backup.sources.rclone.subprocess.run',
                return_value=completed,
            ) as run:
                result = handler.backup()

        command = run.call_args.args[0]
        environment = run.call_args.kwargs['env']
        self.assertEqual(command[:2], ['rclone', 'copy'])
        self.assertNotIn('sync', command)
        self.assertNotIn('not-a-real-secret', command)
        self.assertEqual(
            environment['RCLONE_CONFIG_BACKUPGENIE_TEMP_SECRET_ACCESS_KEY'],
            'not-a-real-secret',
        )
        self.assertEqual(result['files_synced'], 3)
        self.assertEqual(result['size_synced'], 42)

    def test_ssh_passwords_are_process_local(self):
        configurations = (
            (
                SFTPBackup,
                'app.backup.sources.ftp.subprocess.run',
                {'id': 'sftp', 'host': 'nas.example', 'username': 'tester',
                 'password': 'not-a-real-secret'},
            ),
            (
                RsyncSSHBackup,
                'app.backup.sources.rsync_ssh.subprocess.run',
                {'id': 'rsync', 'host': 'nas.example', 'username': 'tester',
                 'password': 'not-a-real-secret'},
            ),
        )
        for handler_class, target, config in configurations:
            with self.subTest(handler=handler_class.__name__):
                calls = []

                def fake_run(command, **kwargs):
                    calls.append((command, kwargs))
                    return self._successful_rsync_result()

                with tempfile.TemporaryDirectory() as destination:
                    with patch(target, side_effect=fake_run):
                        handler_class(config, destination).backup()

                command, kwargs = calls[0]
                self.assertNotIn('not-a-real-secret', command)
                self.assertEqual(kwargs['env']['SSHPASS'], 'not-a-real-secret')
                self.assertNotEqual(os.environ.get('SSHPASS'), 'not-a-real-secret')

    def test_database_cli_credentials_do_not_enter_argv(self):
        mysql_calls = []

        def fake_mysql(command, **kwargs):
            mysql_calls.append((command, kwargs))
            defaults_path = next(
                item.split('=', 1)[1] for item in command
                if item.startswith('--defaults-extra-file=')
            )
            self.assertEqual(os.stat(defaults_path).st_mode & 0o777, 0o600)
            with open(defaults_path, encoding='utf-8') as credential_file:
                self.assertIn('not-a-real-secret', credential_file.read())
            kwargs['stdout'].write('dump')
            return SimpleNamespace(returncode=0, stderr='')

        mysql_config = {
            'id': 'mysql', 'host': 'db.example', 'username': 'tester',
            'password': 'not-a-real-secret', 'database': 'app',
            'options': {'gzip': False, 'compress': False},
        }
        with tempfile.TemporaryDirectory() as destination:
            with patch('app.backup.sources.database.subprocess.run', side_effect=fake_mysql):
                MySQLBackup(mysql_config, destination).backup()
            defaults_path = next(
                item.split('=', 1)[1] for item in mysql_calls[0][0]
                if item.startswith('--defaults-extra-file=')
            )
            self.assertFalse(os.path.exists(defaults_path))
        self.assertNotIn('not-a-real-secret', mysql_calls[0][0])

        mongo_calls = []

        def fake_mongo(command, **kwargs):
            mongo_calls.append((command, kwargs))
            output_path = next(item.split('=', 1)[1] for item in command if item.startswith('--out='))
            os.makedirs(output_path)
            with open(os.path.join(output_path, 'dump.bson'), 'wb') as dump:
                dump.write(b'dump')
            config_path = next(item.split('=', 1)[1] for item in command if item.startswith('--config='))
            self.assertEqual(os.stat(config_path).st_mode & 0o777, 0o600)
            return SimpleNamespace(returncode=0, stdout='', stderr='')

        mongo_config = {
            'id': 'mongo', 'host': 'db.example', 'username': 'tester',
            'password': 'not-a-real-secret', 'database': 'app',
        }
        with tempfile.TemporaryDirectory() as destination:
            with patch('app.backup.sources.database.subprocess.run', side_effect=fake_mongo):
                MongoDBBackup(mongo_config, destination).backup()
            config_path = next(
                item.split('=', 1)[1] for item in mongo_calls[0][0]
                if item.startswith('--config=')
            )
            self.assertFalse(os.path.exists(config_path))
        self.assertNotIn('not-a-real-secret', mongo_calls[0][0])

    def test_influx_token_is_only_in_process_environment(self):
        calls = []

        def fake_run(command, **kwargs):
            calls.append((command, kwargs))
            os.makedirs(command[2], exist_ok=True)
            with open(os.path.join(command[2], 'meta'), 'wb') as file:
                file.write(b'x')
            return SimpleNamespace(returncode=0, stdout='', stderr='')

        config = {
            'id': 'influx', 'host': 'db.example', 'token': 'not-a-real-secret',
            'options': {'compress': False},
        }
        with tempfile.TemporaryDirectory() as destination:
            with patch('app.backup.sources.database.subprocess.run', side_effect=fake_run):
                InfluxDBBackup(config, destination).backup()

        command, kwargs = calls[0]
        self.assertNotIn('not-a-real-secret', command)
        self.assertEqual(kwargs['env']['INFLUX_TOKEN'], 'not-a-real-secret')

    def test_git_remote_url_is_clean_and_auth_is_process_local(self):
        handler = GitBackup(
            {'id': 'git', 'username': 'tester'}, tempfile.gettempdir()
        )
        url, env = handler._repository_access(
            'gitea', 'owner/repo', 'not-a-real-secret', 'git.example'
        )
        self.assertEqual(url, 'https://git.example/owner/repo.git')
        self.assertNotIn('not-a-real-secret', url)
        self.assertNotIn('not-a-real-secret', env['GIT_CONFIG_KEY_0'])
        self.assertIn('AUTHORIZATION: basic ', env['GIT_CONFIG_VALUE_0'])

    def test_ftp_nonzero_raises(self):
        completed = SimpleNamespace(returncode=1, stdout='', stderr='login failed')
        config = {
            'id': 'ftp-test',
            'host': 'nas.example',
            'username': 'tester',
            'password': 'not-a-real-secret',
        }
        with tempfile.TemporaryDirectory() as destination:
            handler = FTPBackup(config, destination)
            with patch('app.backup.sources.ftp.subprocess.run', return_value=completed):
                with self.assertRaisesRegex(Exception, 'lftp failed'):
                    handler.backup()

    def test_unsupported_selfhosted_api_fails(self):
        config = {
            'id': 'unsupported-test',
            'type': 'unsupported-service',
            'options': {'backup_method': 'api'},
        }
        with tempfile.TemporaryDirectory() as destination:
            with self.assertRaisesRegex(Exception, 'No API backup implementation'):
                SelfHostedBackup(config, destination).backup()

    def test_portainer_export_is_https_read_only_and_uses_api_key_header(self):
        calls = []

        class Response:
            def __init__(self, payload):
                self.payload = payload

            def raise_for_status(self):
                return None

            def json(self):
                return self.payload

        def fake_get(url, **kwargs):
            calls.append((url, kwargs))
            if url.endswith('/api/stacks'):
                return Response([{'Id': 7, 'Name': 'test-stack'}])
            if url.endswith('/api/stacks/7/file'):
                return Response({'StackFileContent': 'services: {}'})
            raise AssertionError(f'Unexpected URL: {url}')

        config = {
            'id': 'portainer-test',
            'type': 'portainer',
            'host': 'portainer.example',
            'port': 9443,
            'https': True,
            'api_key': 'not-a-real-secret',
            'backup_method': 'api',
            'options': {'verify_ssl': True},
        }
        with tempfile.TemporaryDirectory() as destination:
            with patch('app.backup.sources.selfhosted.requests.get', side_effect=fake_get):
                result = SelfHostedBackup(config, destination).backup()
            backup_file = next(
                os.path.join(destination, name)
                for name in os.listdir(destination)
                if name.endswith('.json')
            )
            with open(backup_file, encoding='utf-8') as file:
                payload = __import__('json').load(file)

        self.assertEqual(result['files_synced'], 1)
        self.assertEqual(payload['stack_files']['7']['StackFileContent'], 'services: {}')
        self.assertTrue(all(url.startswith('https://') for url, _ in calls))
        self.assertTrue(all(kwargs['headers']['X-API-Key'] == 'not-a-real-secret'
                            for _, kwargs in calls))
        self.assertTrue(all(kwargs['verify'] is True for _, kwargs in calls))

    def test_portainer_connection_test_accepts_api_key_environment(self):
        response = SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: [{'Id': 1}],
        )
        config = {
            'id': 'portainer-test',
            'type': 'portainer',
            'host': 'portainer.example',
            'port': 9443,
            'credentials': {'api_key_env': 'PORTAINER_TEST_KEY'},
        }
        with tempfile.TemporaryDirectory() as destination:
            handler = SelfHostedBackup(config, destination)
            with patch.dict(os.environ, {'PORTAINER_TEST_KEY': 'test-key'}):
                with patch.object(handler, '_api_get', return_value=response) as get:
                    self.assertEqual(handler.test_connection(), 1)

        self.assertEqual(
            get.call_args.kwargs['headers'], {'X-API-Key': 'test-key'}
        )
        self.assertEqual(
            get.call_args.args[0], 'https://portainer.example:9443/api/stacks'
        )

    def test_sqlite_uses_consistent_backup_api(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source_path = os.path.join(temp_dir, 'live.sqlite')
            destination = os.path.join(temp_dir, 'backup')
            os.makedirs(destination)

            source = sqlite3.connect(source_path)
            try:
                source.execute('PRAGMA journal_mode=WAL')
                source.execute('CREATE TABLE entries (value TEXT)')
                source.execute('INSERT INTO entries VALUES (?)', ('kept',))
                source.commit()

                result = SQLiteBackup(
                    {'id': 'sqlite-test', 'databases': [source_path]},
                    destination,
                ).backup()
            finally:
                source.close()

            backup_files = [
                os.path.join(destination, name)
                for name in os.listdir(destination)
                if name.endswith('.db')
            ]
            self.assertEqual(result['files_synced'], 1)
            self.assertEqual(len(backup_files), 1)
            with closing(sqlite3.connect(backup_files[0])) as restored:
                self.assertEqual(restored.execute('SELECT value FROM entries').fetchone()[0], 'kept')

    def test_redis_streams_remote_rdb_without_password_in_argv(self):
        calls = []

        def fake_run(cmd, **kwargs):
            calls.append((cmd, kwargs))
            target = cmd[cmd.index('--rdb') + 1]
            with open(target, 'wb') as file:
                file.write(b'REDIS0009-test')
            return SimpleNamespace(returncode=0, stdout='Transfer finished', stderr='')

        config = {
            'id': 'redis-test',
            'host': 'redis.example',
            'password': 'not-a-real-secret',
        }
        with tempfile.TemporaryDirectory() as destination:
            with patch('app.backup.sources.database.subprocess.run', side_effect=fake_run):
                result = RedisBackup(config, destination).backup()

        command, kwargs = calls[0]
        self.assertEqual(result['files_synced'], 1)
        self.assertNotIn('not-a-real-secret', command)
        self.assertEqual(kwargs['env']['REDISCLI_AUTH'], 'not-a-real-secret')

    def test_docker_restarts_stopped_container_after_backup_failure(self):
        calls = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            if cmd[:2] == ['docker', 'ps']:
                return SimpleNamespace(returncode=0, stdout='container-1\n', stderr='')
            if cmd[:2] == ['docker', 'stop']:
                return SimpleNamespace(returncode=0, stdout='container-1', stderr='')
            if cmd[:2] == ['docker', 'run']:
                return SimpleNamespace(returncode=1, stdout='', stderr='tar failed')
            if cmd[:2] == ['docker', 'start']:
                return SimpleNamespace(returncode=0, stdout='container-1', stderr='')
            raise AssertionError(f'Unexpected command: {cmd}')

        config = {
            'id': 'docker-test',
            'volumes': ['data'],
            'options': {'stop_for_backup': True},
        }
        with tempfile.TemporaryDirectory() as destination:
            with patch('app.backup.sources.docker.subprocess.run', side_effect=fake_run):
                with self.assertRaisesRegex(Exception, 'Docker volume backup failed'):
                    DockerVolumeBackup(config, destination).backup()

        self.assertIn(['docker', 'start', 'container-1'], calls)


class ExecutorResultTests(unittest.TestCase):
    class PartialHandler(BackupHandler):
        def backup(self):
            return {
                'files_synced': 1,
                'size_synced': 42,
                'logs': 'Copied first item\nERROR: second item failed',
            }

    def test_executor_persists_partial_instead_of_completed(self):
        app = Flask('backup-result-test')
        app.config.update(
            SQLALCHEMY_DATABASE_URI='sqlite:///:memory:',
            SQLALCHEMY_TRACK_MODIFICATIONS=False,
        )
        db.init_app(app)

        with tempfile.TemporaryDirectory() as destination, app.app_context():
            db.create_all()
            backup = Backup(backup_id='result-contract-test', status='running')
            db.session.add(backup)
            db.session.flush()
            db.session.add(BackupSourceResult(
                backup_id=backup.id,
                source_id='partial-source',
                source_name='Partial source',
                source_type='partial-test',
                status='pending',
            ))
            db.session.commit()

            executor = BackupExecutor(
                'result-contract-test', enable_notifications=False, app=app
            )
            executor.backup_base_path = destination
            executor.handlers = {'partial-test': self.PartialHandler}

            result = executor._backup_source({
                'id': 'partial-source',
                'name': 'Partial source',
                'type': 'partial-test',
            })

            stored = BackupSourceResult.query.one()
            self.assertEqual(result['status'], 'partial')
            self.assertEqual(stored.status, 'partial')
            self.assertIn('second item failed', stored.error_message)
            db.session.remove()
            db.engine.dispose()


if __name__ == '__main__':
    unittest.main(verbosity=2)
