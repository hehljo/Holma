"""Helpers for keeping PostgreSQL passwords out of process arguments."""
import os
from urllib.parse import parse_qsl, quote, unquote, urlencode, urlsplit, urlunsplit


def safe_postgres_command(connection_string, base_env=None):
    """Return a password-free URI and libpq environment for subprocesses."""
    parsed = urlsplit(connection_string)
    if parsed.scheme not in ('postgres', 'postgresql') or not parsed.hostname:
        raise ValueError('Invalid PostgreSQL connection URL')

    password = unquote(parsed.password) if parsed.password is not None else ''
    username = quote(unquote(parsed.username), safe='') if parsed.username else ''
    hostname = parsed.hostname
    if ':' in hostname and not hostname.startswith('['):
        hostname = f'[{hostname}]'
    host_port = hostname + (f':{parsed.port}' if parsed.port else '')
    netloc = f'{username}@{host_port}' if username else host_port

    query_items = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        if key.lower() == 'password':
            if not password:
                password = value
            continue
        query_items.append((key, value))

    safe_url = urlunsplit((
        parsed.scheme,
        netloc,
        parsed.path,
        urlencode(query_items),
        parsed.fragment,
    ))
    env = dict(base_env if base_env is not None else os.environ)
    if password:
        env['PGPASSWORD'] = password
    return safe_url, env
