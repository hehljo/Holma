#!/usr/bin/env python3
"""Security regressions for auth, settings and encrypted configuration."""

import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

from flask import Flask
from werkzeug.security import generate_password_hash


BACKEND_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

from app import db, limiter
from app.api.auth import auth_bp
from app.api.config import config_bp
from app.api.settings import settings_bp
from app.api.sources import sources_bp
from app.config import Config
from app.models.backup import Setting, User
from app.notifications.channels import EmailNotification, TelegramNotification
from app.postgres_utils import safe_postgres_command
from app.source_config import REDACTED_VALUE, load_sources, migrate_source_secrets
import app.crypto as crypto


class SecurityApiTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.backup_root = os.path.join(self.temp_dir.name, 'backup')
        os.makedirs(self.backup_root)
        self.sources_path = os.path.join(self.temp_dir.name, 'sources.json')
        self.secret = 'test-secret-key-that-is-long-enough-123456789'
        self.patches = [
            patch.object(Config, 'SECRET_KEY', self.secret),
            patch.object(Config, 'JWT_SECRET_KEY', self.secret),
            patch.object(Config, 'BACKUP_BASE_PATH', self.backup_root),
            patch.object(Config, 'SOURCES_CONFIG_PATH', self.sources_path),
        ]
        for active_patch in self.patches:
            active_patch.start()
        crypto._fernet = None

        self.app = Flask('security-api-test')
        self.app.config.update(
            SECRET_KEY=self.secret,
            SQLALCHEMY_DATABASE_URI='sqlite:///:memory:',
            SQLALCHEMY_TRACK_MODIFICATIONS=False,
            RATELIMIT_ENABLED=False,
            TESTING=True,
        )
        db.init_app(self.app)
        limiter.init_app(self.app)
        self.app.register_blueprint(auth_bp, url_prefix='/api/v1/auth')
        self.app.register_blueprint(config_bp, url_prefix='/api/v1/config')
        self.app.register_blueprint(settings_bp, url_prefix='/api/v1/settings')
        self.app.register_blueprint(sources_bp, url_prefix='/api/v1/sources')
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        db.session.add(User(
            username='admin',
            password_hash=generate_password_hash('CurrentPass123!'),
        ))
        db.session.commit()
        self.client = self.app.test_client()
        self.admin_token = self._login('admin', 'CurrentPass123!')

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        db.engine.dispose()
        self.context.pop()
        crypto._fernet = None
        for active_patch in reversed(self.patches):
            active_patch.stop()
        self.temp_dir.cleanup()

    def _login(self, username, password):
        response = self.client.post('/api/v1/auth/login', json={
            'username': username,
            'password': password,
        })
        self.assertEqual(response.status_code, 200, response.get_json())
        return response.get_json()['access_token']

    @staticmethod
    def _headers(token):
        return {'Authorization': f'Bearer {token}'}

    def test_viewer_cannot_change_settings(self):
        response = self.client.post(
            '/api/v1/auth/register',
            headers=self._headers(self.admin_token),
            json={
                'username': 'viewer',
                'password': 'ViewerPassword123!',
                'role': 'viewer',
            },
        )
        self.assertEqual(response.status_code, 201)
        viewer_token = self._login('viewer', 'ViewerPassword123!')

        denied = self.client.put(
            '/api/v1/settings',
            headers=self._headers(viewer_token),
            json={'max_parallel_tasks': 3},
        )
        self.assertEqual(denied.status_code, 403)

    def test_password_change_requires_current_and_revokes_old_token(self):
        denied = self.client.put(
            '/api/v1/auth/password',
            headers=self._headers(self.admin_token),
            json={'current_password': 'wrong', 'new_password': 'NewPassword123!'},
        )
        self.assertEqual(denied.status_code, 403)

        changed = self.client.put(
            '/api/v1/auth/password',
            headers=self._headers(self.admin_token),
            json={
                'current_password': 'CurrentPass123!',
                'new_password': 'NewPassword123!',
            },
        )
        self.assertEqual(changed.status_code, 200)
        self.assertIn('access_token', changed.get_json())
        old_token = self.client.get(
            '/api/v1/auth/me', headers=self._headers(self.admin_token)
        )
        self.assertEqual(old_token.status_code, 401)

    def test_automation_token_requires_password_and_is_revocable(self):
        denied = self.client.post(
            '/api/v1/auth/api-token',
            headers=self._headers(self.admin_token),
            json={'current_password': 'wrong', 'expires_days': 365},
        )
        self.assertEqual(denied.status_code, 403)

        invalid_lifetime = self.client.post(
            '/api/v1/auth/api-token',
            headers=self._headers(self.admin_token),
            json={'current_password': 'CurrentPass123!', 'expires_days': 366},
        )
        self.assertEqual(invalid_lifetime.status_code, 400)

        created = self.client.post(
            '/api/v1/auth/api-token',
            headers=self._headers(self.admin_token),
            json={'current_password': 'CurrentPass123!', 'expires_days': 365},
        )
        self.assertEqual(created.status_code, 201, created.get_json())
        token_data = created.get_json()
        self.assertEqual(token_data['token_type'], 'Bearer')
        self.assertEqual(token_data['expires_in'], 365 * 24 * 60 * 60)

        automation_token = token_data['access_token']
        allowed = self.client.get(
            '/api/v1/auth/me', headers=self._headers(automation_token)
        )
        self.assertEqual(allowed.status_code, 200)

        changed = self.client.put(
            '/api/v1/auth/password',
            headers=self._headers(self.admin_token),
            json={
                'current_password': 'CurrentPass123!',
                'new_password': 'NewPassword123!',
            },
        )
        self.assertEqual(changed.status_code, 200)
        revoked = self.client.get(
            '/api/v1/auth/me', headers=self._headers(automation_token)
        )
        self.assertEqual(revoked.status_code, 401)

    def test_remote_init_is_disabled_without_setup_token(self):
        denied = self.client.post('/api/v1/auth/init')
        self.assertEqual(denied.status_code, 403)

    def test_source_secret_is_encrypted_redacted_and_preserved_on_update(self):
        created = self.client.post(
            '/api/v1/sources',
            headers=self._headers(self.admin_token),
            json={
                'id': 'smb-secure',
                'name': 'Secure SMB',
                'type': 'smb',
                'config': {
                    'host': 'diskstation',
                    'password': 'inline-test-password',
                },
            },
        )
        self.assertEqual(created.status_code, 201, created.get_json())
        self.assertEqual(
            created.get_json()['source']['config']['password'], REDACTED_VALUE
        )
        with open(self.sources_path, 'r', encoding='utf-8') as file:
            raw_text = file.read()
        self.assertNotIn('inline-test-password', raw_text)
        self.assertIn('ENC::', raw_text)
        self.assertEqual(
            load_sources()[0]['config']['password'], 'inline-test-password'
        )

        api_source = self.client.get(
            '/api/v1/sources/smb-secure',
            headers=self._headers(self.admin_token),
        ).get_json()
        api_source['name'] = 'Renamed SMB'
        updated = self.client.put(
            '/api/v1/sources/smb-secure',
            headers=self._headers(self.admin_token),
            json=api_source,
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(
            load_sources()[0]['config']['password'], 'inline-test-password'
        )

    def test_legacy_plaintext_source_secret_is_migrated_without_data_loss(self):
        with open(self.sources_path, 'w', encoding='utf-8') as file:
            json.dump({'backup_sources': [{
                'id': 'legacy',
                'name': 'Legacy',
                'type': 'smb',
                'config': {'host': 'diskstation', 'password': 'legacy-secret'},
            }]}, file)

        self.assertTrue(migrate_source_secrets())
        with open(self.sources_path, 'r', encoding='utf-8') as file:
            raw_text = file.read()
        self.assertNotIn('legacy-secret', raw_text)
        self.assertEqual(load_sources()[0]['config']['password'], 'legacy-secret')

    def test_config_import_applies_settings_and_never_stores_redaction_marker(self):
        response = self.client.post(
            '/api/v1/config/import',
            headers=self._headers(self.admin_token),
            json={
                'version': '1.0',
                'sources': [{
                    'id': 'imported',
                    'name': 'Imported',
                    'type': 'smb',
                    'config': {
                        'host': 'diskstation',
                        'password': REDACTED_VALUE,
                    },
                }],
                'settings': {'max_parallel_tasks': 3},
            },
        )
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual(Setting.get('max_parallel_tasks'), '3')
        with open(self.sources_path, 'r', encoding='utf-8') as file:
            raw_text = file.read()
        self.assertNotIn(REDACTED_VALUE, raw_text)
        self.assertNotIn('password', load_sources()[0]['config'])

    def test_invalid_import_settings_do_not_change_sources(self):
        original = {
            'version': '1.0',
            'sources': [{'id': 'bad-import', 'name': 'Bad', 'type': 'local'}],
            'settings': {'max_parallel_tasks': 99},
        }
        response = self.client.post(
            '/api/v1/config/import',
            headers=self._headers(self.admin_token),
            json=original,
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(os.path.exists(self.sources_path))

    def test_unsupported_connection_test_is_not_reported_as_success(self):
        self.client.post(
            '/api/v1/sources',
            headers=self._headers(self.admin_token),
            json={'id': 'unsupported', 'name': 'Unsupported', 'type': 'unknown'},
        )
        response = self.client.post(
            '/api/v1/sources/unsupported/test',
            headers=self._headers(self.admin_token),
        )
        self.assertEqual(response.status_code, 501)
        self.assertEqual(response.get_json()['status'], 'unsupported')

    def test_settings_are_atomic_and_backup_path_is_restricted(self):
        response = self.client.put(
            '/api/v1/settings',
            headers=self._headers(self.admin_token),
            json={'max_parallel_tasks': 4, 'backup_base_path': '/etc'},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIsNone(Setting.query.filter_by(key='max_parallel_tasks').first())

        allowed = os.path.join(self.backup_root, 'secondary')
        response = self.client.put(
            '/api/v1/settings',
            headers=self._headers(self.admin_token),
            json={'max_parallel_tasks': 4, 'backup_base_path': allowed},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Setting.get('max_parallel_tasks'), '4')

    def test_notification_channels_use_encrypted_ui_credentials(self):
        Setting.set('credential.smtp_password', 'smtp-ui-secret')
        Setting.set('credential.telegram_bot_token', 'telegram-ui-secret')

        email = EmailNotification({
            'smtp_host': 'smtp.example',
            'smtp_user': 'user',
            'smtp_password': 'file-secret',
            'from_email': 'from@example.com',
            'to_emails': ['to@example.com'],
        })
        telegram = TelegramNotification({
            'bot_token': 'file-token',
            'chat_ids': ['1'],
        })
        self.assertEqual(email.smtp_password, 'smtp-ui-secret')
        self.assertEqual(telegram.bot_token, 'telegram-ui-secret')


class PostgresCredentialTests(unittest.TestCase):
    def test_password_is_removed_from_process_argument(self):
        connection, env = safe_postgres_command(
            'postgresql://user:p%40ss@db.example:5432/database?sslmode=require'
        )
        self.assertNotIn('p%40ss', connection)
        self.assertNotIn('p@ss', connection)
        self.assertEqual(env['PGPASSWORD'], 'p@ss')
        self.assertIn('sslmode=require', connection)


if __name__ == '__main__':
    unittest.main(verbosity=2)
