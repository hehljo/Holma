"""First-run setup and local offline account recovery regressions."""
import io
from concurrent.futures import ThreadPoolExecutor
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

BACKEND_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

from app import create_app, db
from app.account_cli import main
from app.config import Config
from app.models.backup import User


class FirstRunTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = self.temp.name
        self.patches = [
            patch.object(Config, 'SQLALCHEMY_DATABASE_URI', f'sqlite:///{root}/test.db'),
            patch.object(Config, 'SECRET_KEY', 'first-run-test-secret-key-123456789'),
            patch.object(Config, 'JWT_SECRET_KEY', 'first-run-test-secret-key-123456789'),
            patch.object(Config, 'APP_INIT_LOCK_PATH', f'{root}/init.lock'),
            patch.object(Config, 'SOURCES_CONFIG_PATH', f'{root}/sources.json'),
            patch.dict(os.environ, {'NOTIFICATION_CONFIG_PATH': f'{root}/notifications.json'}),
            patch.object(Config, 'LOG_FILE', f'{root}/app.log'),
        ]
        for active in self.patches:
            active.start()
        self.app = create_app()
        self.app.config['RATELIMIT_ENABLED'] = False
        self.client = self.app.test_client()

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.engine.dispose()
        for active in reversed(self.patches):
            active.stop()
        self.temp.cleanup()

    def command(self, *args, passwords=()):
        output = io.StringIO()
        with patch.object(sys, 'argv', ['account_cli', *args]), \
                patch('sys.stdout', output), \
                patch('app.account_cli.getpass.getpass', side_effect=passwords):
            main()
        return output.getvalue().strip()

    @staticmethod
    def owner_data(name='owner', password='SafePassword123!'):
        return {
            'username': name, 'password': password,
            'confirm_password': password,
        }

    def test_first_run_requires_confirmation_and_does_not_reopen(self):
        self.assertTrue(self.client.get('/api/v1/auth/setup/status').json['needs_setup'])
        payload = self.owner_data()
        del payload['confirm_password']
        self.assertEqual(self.client.post('/api/v1/auth/setup', json=payload).status_code, 400)
        payload['confirm_password'] = 'DifferentPassword123!'
        self.assertEqual(self.client.post('/api/v1/auth/setup', json=payload).status_code, 400)
        payload['confirm_password'] = payload['password']
        self.assertEqual(self.client.post('/api/v1/auth/setup', json=payload).status_code, 201)
        self.assertFalse(self.client.get('/api/v1/auth/setup/status').json['needs_setup'])
        self.assertEqual(self.client.post('/api/v1/auth/setup', json=self.owner_data('other')).status_code, 409)
        self.assertEqual(self.client.post('/api/v1/auth/login', json={
            'username': 'owner', 'password': payload['password'],
        }).status_code, 200)
        # A container restart with the same database must not re-open first-run setup.
        restarted = create_app()
        restarted.config['RATELIMIT_ENABLED'] = False
        self.assertFalse(restarted.test_client().get('/api/v1/auth/setup/status').json['needs_setup'])
        with restarted.app_context():
            db.session.remove()
            db.engine.dispose()

    def test_concurrent_setup_creates_exactly_one_owner(self):
        def setup(name):
            with self.app.test_client() as client:
                return client.post('/api/v1/auth/setup', json=self.owner_data(name)).status_code

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(setup, ('owner_a', 'owner_b')))
        self.assertEqual(sorted(results), [201, 409])
        with self.app.app_context():
            self.assertEqual(User.query.count(), 1)

    def test_setup_validation_and_offline_password_reset_revokes_token(self):
        self.assertEqual(self.client.post('/api/v1/auth/setup', json=self.owner_data('owner', '')).status_code, 400)
        self.assertEqual(self.client.post('/api/v1/auth/setup', json=self.owner_data('!invalid')).status_code, 400)
        self.assertEqual(self.client.post('/api/v1/auth/setup', json=self.owner_data()).status_code, 201)
        login = self.client.post('/api/v1/auth/login', json={
            'username': 'owner', 'password': 'SafePassword123!',
        })
        token = login.json['access_token']
        self.assertEqual(self.command('list-users'), 'owner')
        self.command('reset-password', 'owner', passwords=('AnotherSafe123!', 'AnotherSafe123!'))
        self.assertEqual(self.client.get('/api/v1/auth/me', headers={
            'Authorization': f'Bearer {token}',
        }).status_code, 401)
        self.assertEqual(self.client.post('/api/v1/auth/login', json={
            'username': 'owner', 'password': 'SafePassword123!',
        }).status_code, 401)
        self.assertEqual(self.client.post('/api/v1/auth/login', json={
            'username': 'owner', 'password': 'AnotherSafe123!',
        }).status_code, 200)
        with self.app.app_context():
            self.assertEqual(User.query.count(), 1)

    def test_unicode_and_short_passwords_across_setup_login_change_and_reset(self):
        payload = self.owner_data(password='ß🦉')
        payload['confirm_password'] = 'ß🦊'
        self.assertEqual(self.client.post('/api/v1/auth/setup', json=payload).status_code, 400)
        payload['confirm_password'] = 'ß🦉'
        self.assertEqual(self.client.post('/api/v1/auth/setup', json=payload).status_code, 201)
        login = self.client.post('/api/v1/auth/login', json={
            'username': 'owner', 'password': 'ß🦉',
        })
        self.assertEqual(login.status_code, 200)
        changed = self.client.put('/api/v1/auth/password', json={
            'current_password': 'ß🦉', 'new_password': '🦊',
        }, headers={'Authorization': f"Bearer {login.json['access_token']}"})
        self.assertEqual(changed.status_code, 200)
        self.assertEqual(self.client.post('/api/v1/auth/login', json={
            'username': 'owner', 'password': '🦊',
        }).status_code, 200)
        self.command('reset-password', 'owner', passwords=('ß', 'ß'))
        self.assertEqual(self.client.post('/api/v1/auth/login', json={
            'username': 'owner', 'password': 'ß',
        }).status_code, 200)
        self.assertEqual(self.client.post('/api/v1/auth/login', json={
            'username': 'owner', 'password': '\ud800',
        }).status_code, 401)


if __name__ == '__main__':
    unittest.main()
