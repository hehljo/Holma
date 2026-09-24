"""Local-only first-run access code; never expose its contents via HTTP or logs."""
import os
import secrets
import stat

from app.config import Config


def read_setup_token():
    """Return the container-local code only when it is a protected regular file."""
    try:
        fd = os.open(Config.SETUP_TOKEN_PATH, os.O_RDONLY | os.O_NOFOLLOW)
    except FileNotFoundError:
        return None
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077 or info.st_uid != os.geteuid():
            return None
        with os.fdopen(fd, 'r', encoding='ascii') as token_file:
            fd = -1
            return token_file.read(257).strip()
    finally:
        if fd != -1:
            os.close(fd)


def ensure_setup_token():
    """Create a persistent one-time code with exclusive permissions if absent."""
    existing = read_setup_token()
    if existing:
        return existing
    code = secrets.token_urlsafe(32)
    try:
        fd = os.open(
            Config.SETUP_TOKEN_PATH,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
        )
    except FileExistsError:
        existing = read_setup_token()
        if not existing:
            raise RuntimeError('Setup code file is not readable or protected')
        return existing
    with os.fdopen(fd, 'w', encoding='ascii') as token_file:
        token_file.write(code + '\n')
    return code
