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
            patch.object(Config, 'SETUP_TOKEN_PATH', f'{root}/setup-token'),
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

    def test_first_run_requires_local_code_and_does_not_reopen(self):
        self.assertTrue(self.client.get('/api/v1/auth/setup/status').json['needs_setup'])
        payload = {'username': 'owner', 'password': 'SafePassword123!', 'setup_code': 'wrong'}
        self.assertEqual(self.client.post('/api/v1/auth/setup', json=payload).status_code, 403)
        code = self.command('setup-code')
        self.assertTrue(code)
        self.assertEqual(code, self.command('setup-code'))
        self.assertEqual(os.stat(Config.SETUP_TOKEN_PATH).st_mode & 0o777, 0o600)
        payload['setup_code'] = code
        self.assertEqual(self.client.post('/api/v1/auth/setup', json=payload).status_code, 201)
        self.assertFalse(self.client.get('/api/v1/auth/setup/status').json['needs_setup'])
        self.assertEqual(self.client.post('/api/v1/auth/setup', json={
            'username': 'attacker', 'password': 'SafePassword123!', 'setup_code': code,
        }).status_code, 409)
        with self.assertRaises(SystemExit):
            self.command('setup-code')
        self.assertEqual(self.client.post('/api/v1/auth/login', json={
            'username': 'owner', 'password': 'SafePassword123!',
        }).status_code, 200)

    def test_concurrent_setup_creates_exactly_one_owner(self):
        code = self.command('setup-code')

        def setup(name):
            with self.app.test_client() as client:
                return client.post('/api/v1/auth/setup', json={
                    'username': name, 'password': 'SafePassword123!', 'setup_code': code,
                }).status_code

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(setup, ('owner_a', 'owner_b')))
        self.assertEqual(sorted(results), [201, 409])
        with self.app.app_context():
            self.assertEqual(User.query.count(), 1)

    def test_setup_validation_and_offline_password_reset_revokes_token(self):
        code = self.command('setup-code')
        payload = {'username': 'owner', 'password': 'weak', 'setup_code': code}
        self.assertEqual(self.client.post('/api/v1/auth/setup', json=payload).status_code, 400)
        payload['password'] = 'SafePassword123!'
        self.assertEqual(self.client.post('/api/v1/auth/setup', json=payload).status_code, 201)
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


if __name__ == '__main__':
    unittest.main()
