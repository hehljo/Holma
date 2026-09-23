"""Short-lived, mode-0600 credential files for command-line clients."""
from contextlib import contextmanager
import json
import os
import tempfile


def _mysql_escape(value):
    return (
        str(value)
        .replace('\\', '\\\\')
        .replace('"', '\\"')
        .replace('\n', '\\n')
        .replace('\r', '\\r')
    )


@contextmanager
def mysql_defaults_file(host, port, username, password):
    """Create a MySQL client option file so credentials never enter argv."""
    path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode='w', encoding='utf-8', prefix='.backupgenie-mysql-',
            suffix='.cnf', delete=False,
        ) as file:
            path = file.name
            file.write('[client]\n')
            file.write(f'host="{_mysql_escape(host)}"\n')
            file.write(f'port={int(port)}\n')
            file.write(f'user="{_mysql_escape(username)}"\n')
            file.write(f'password="{_mysql_escape(password)}"\n')
        os.chmod(path, 0o600)
        yield path
    finally:
        if path and os.path.exists(path):
            os.unlink(path)


@contextmanager
def mongodb_password_file(password):
    """Create the protected YAML/JSON config recommended by mongodump."""
    path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode='w', encoding='utf-8', prefix='.backupgenie-mongodb-',
            suffix='.yml', delete=False,
        ) as file:
            path = file.name
            json.dump({'password': str(password)}, file)
        os.chmod(path, 0o600)
        yield path
    finally:
        if path and os.path.exists(path):
            os.unlink(path)
