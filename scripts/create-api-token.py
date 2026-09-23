#!/usr/bin/env python3
"""Interactively create and store a Holma automation token."""

import argparse
import getpass
import json
import os
from pathlib import Path
import tempfile
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


def _validated_api_url(value):
    base_url = value.rstrip('/')
    parsed = urlparse(base_url)
    if parsed.scheme not in ('http', 'https') or not parsed.hostname:
        raise ValueError('API URL must use http:// or https://')
    if parsed.scheme == 'http' and parsed.hostname not in (
        '127.0.0.1', 'localhost', '::1'
    ):
        raise ValueError('Plain HTTP is only allowed for a local API URL')
    if parsed.query or parsed.fragment or parsed.username or parsed.password:
        raise ValueError('API URL must not contain credentials, query or fragment')
    return base_url


def _post_json(url, payload, token=None):
    headers = {'Content-Type': 'application/json'}
    if token:
        headers['Authorization'] = f'Bearer {token}'
    request = Request(
        url,
        data=json.dumps(payload).encode('utf-8'),
        headers=headers,
        method='POST',
    )
    try:
        with urlopen(request, timeout=30) as response:  # nosec B310
            return json.loads(response.read().decode('utf-8'))
    except HTTPError as error:
        try:
            detail = json.loads(error.read().decode('utf-8')).get('error')
        except (ValueError, UnicodeDecodeError):
            detail = None
        raise RuntimeError(detail or f'API returned HTTP {error.code}') from error
    except URLError as error:
        raise RuntimeError(f'API is not reachable: {error.reason}') from error


def _store_token(output_path, token):
    target = Path(output_path).expanduser()
    if target.exists():
        raise RuntimeError(
            f'{target} already exists; keep it or remove it deliberately first'
        )
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix='.holma-token-', dir=str(target.parent)
    )
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, 'w', encoding='utf-8') as token_file:
            token_file.write(token)
            token_file.write('\n')
            token_file.flush()
            os.fsync(token_file.fileno())
        os.replace(temporary_name, target)
    except Exception:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def main():
    parser = argparse.ArgumentParser(
        description='Create a password-bound Holma automation token.'
    )
    parser.add_argument(
        '--api-url',
        default='http://127.0.0.1:5000/api/v1',
        help='API root; plain HTTP is accepted only on localhost',
    )
    parser.add_argument('--username', default='admin')
    parser.add_argument('--expires-days', type=int, default=365)
    parser.add_argument(
        '--output', default='/etc/holma/api_token'
    )
    args = parser.parse_args()

    password = None
    try:
        api_url = _validated_api_url(args.api_url)
        password = getpass.getpass(f'Password for {args.username}: ')
        login = _post_json(
            f'{api_url}/auth/login',
            {'username': args.username, 'password': password},
        )
        created = _post_json(
            f'{api_url}/auth/api-token',
            {
                'current_password': password,
                'expires_days': args.expires_days,
            },
            token=login['access_token'],
        )
        _store_token(args.output, created['access_token'])
    except (KeyError, OSError, RuntimeError, ValueError) as error:
        parser.exit(1, f'Error: {error}\n')
    finally:
        password = None

    print(
        f'Automation token stored with mode 0600 at {args.output} '
        f'(valid for {args.expires_days} days).'
    )
    print('Changing the account password revokes it immediately.')


if __name__ == '__main__':
    main()
