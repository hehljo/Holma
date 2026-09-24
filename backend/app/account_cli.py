"""Offline account recovery from the backend container console."""
import argparse
import getpass
import sys

from werkzeug.security import generate_password_hash

from app import create_app, db, _app_init_lock
from app.api.auth import validate_password
from app.config import Config
from app.models.backup import User


def main():
    parser = argparse.ArgumentParser(description='Local account access management')
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('list-users', help='List account names (no credentials)')
    reset = commands.add_parser('reset-password', help='Reset an existing account password')
    reset.add_argument('username')
    args = parser.parse_args()

    app = create_app()
    with app.app_context(), _app_init_lock(Config):
        if args.command == 'list-users':
            for (username,) in db.session.query(User.username).order_by(User.id):
                print(username)
        else:
            user = User.query.filter_by(username=args.username).first()
            if user is None:
                parser.error('Account not found')
            password = getpass.getpass('New password: ')
            valid, error = validate_password(password)
            if not valid:
                parser.error(error)
            if password != getpass.getpass('Repeat new password: '):
                parser.error('Passwords do not match')
            user.password_hash = generate_password_hash(password)
            db.session.commit()
            print('Password changed; previous login and automation tokens are revoked.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
