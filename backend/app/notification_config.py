"""Encrypted-at-rest notification configuration."""
import json
import logging
import os
import tempfile

from app.crypto import decrypt_value, encrypt_value

logger = logging.getLogger(__name__)

PREFIX = 'ENC::'
SENSITIVE_KEYS = {
    'smtp_password', 'webhook_url', 'bot_token', 'password', 'topic', 'urls',
}


def _transform(value, key=None, decrypt=False):
    if isinstance(value, dict):
        return {
            child_key: _transform(child, child_key, decrypt)
            for child_key, child in value.items()
        }
    if isinstance(value, list):
        return [_transform(child, key, decrypt) for child in value]
    if key not in SENSITIVE_KEYS or not isinstance(value, str) or not value:
        return value
    if decrypt:
        return decrypt_value(value[len(PREFIX):]) if value.startswith(PREFIX) else value
    return value if value.startswith(PREFIX) else PREFIX + encrypt_value(value)


def load_notification_config(path):
    with open(path, 'r', encoding='utf-8') as file:
        return _transform(json.load(file), decrypt=True)


def migrate_notification_secrets(path):
    if not os.path.isfile(path):
        return False
    with open(path, 'r', encoding='utf-8') as file:
        raw = json.load(file)
    encrypted = _transform(raw)
    if encrypted == raw:
        return False

    directory = os.path.dirname(path) or '.'
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode='w', encoding='utf-8', dir=directory,
            prefix='.notifications-', suffix='.tmp', delete=False,
        ) as temp_file:
            temp_path = temp_file.name
            json.dump(encrypted, temp_file, indent=2)
            temp_file.flush()
            os.fsync(temp_file.fileno())
        os.chmod(temp_path, 0o600)
        os.replace(temp_path, path)
    except Exception:
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)
        raise
    logger.info('Encrypted legacy notification credentials')
    return True
