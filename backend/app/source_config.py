"""Safe persistence and API presentation of backup source configuration."""
import json
import logging
import os
import tempfile

from app.config import Config
from app.crypto import decrypt_value, encrypt_value

logger = logging.getLogger(__name__)

ENCRYPTED_PREFIX = 'ENC::'
REDACTED_VALUE = '***REDACTED***'


def is_sensitive_key(key):
    """Identify inline credentials while excluding env/path references."""
    normalized = str(key).lower()
    if normalized.endswith(('_env', '_path', '_file')):
        return False
    if normalized in {
        'password', 'passwd', 'token', 'secret', 'key', 'authorization',
        'connection_string', 'webhook_url', 'private_key', 'ssh_key',
    }:
        return True
    return any(fragment in normalized for fragment in (
        'password', 'passwd', 'api_key', 'access_key', 'secret_key',
        'service_role_key', 'private_key', 'auth_token', 'access_token',
        'refresh_token',
    ))


def _transform_sensitive(value, transform):
    if isinstance(value, dict):
        transformed = {}
        for key, item in value.items():
            if is_sensitive_key(key) and isinstance(item, str):
                transformed[key] = transform(item)
            else:
                transformed[key] = _transform_sensitive(item, transform)
        return transformed
    if isinstance(value, list):
        return [_transform_sensitive(item, transform) for item in value]
    return value


def encrypt_source_secrets(sources):
    """Encrypt direct source credentials while leaving env references intact."""
    def encrypt(item):
        if not item or item == REDACTED_VALUE or item.startswith(ENCRYPTED_PREFIX):
            return item
        return ENCRYPTED_PREFIX + encrypt_value(item)

    return _transform_sensitive(sources, encrypt)


def decrypt_source_secrets(sources):
    """Decrypt encrypted source credentials for internal handler use only."""
    def decrypt(item):
        if not item.startswith(ENCRYPTED_PREFIX):
            return item
        return decrypt_value(item[len(ENCRYPTED_PREFIX):])

    return _transform_sensitive(sources, decrypt)


def redact_source_secrets(sources):
    """Return an API-safe copy that never exposes inline credentials."""
    def redact(item):
        return REDACTED_VALUE if item else item

    return _transform_sensitive(sources, redact)


def strip_redaction_markers(value):
    """Drop redacted secret placeholders before importing exported config."""
    if isinstance(value, dict):
        cleaned = {}
        for key, item in value.items():
            if is_sensitive_key(key) and item == REDACTED_VALUE:
                continue
            cleaned[key] = strip_redaction_markers(item)
        return cleaned
    if isinstance(value, list):
        return [strip_redaction_markers(item) for item in value]
    return value


def merge_preserving_redacted(existing, update):
    """Merge an API update without replacing stored secrets by placeholders."""
    if not isinstance(existing, dict) or not isinstance(update, dict):
        return existing if update == REDACTED_VALUE else update

    merged = dict(existing)
    for key, value in update.items():
        if is_sensitive_key(key) and value == REDACTED_VALUE:
            continue
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = merge_preserving_redacted(merged[key], value)
        else:
            merged[key] = value
    return merged


def _read_raw_sources():
    try:
        with open(Config.SOURCES_CONFIG_PATH, 'r', encoding='utf-8') as file:
            data = json.load(file)
    except FileNotFoundError:
        return []
    except (json.JSONDecodeError, OSError) as exc:
        logger.error('Could not load source configuration: %s', type(exc).__name__)
        return []

    sources = data.get('backup_sources', []) if isinstance(data, dict) else []
    return sources if isinstance(sources, list) else []


def load_sources(*, redact=False):
    """Load decrypted sources internally or a redacted copy for API output."""
    sources = decrypt_source_secrets(_read_raw_sources())
    return redact_source_secrets(sources) if redact else sources


def save_sources(sources):
    """Atomically save source configuration with inline secrets encrypted."""
    directory = os.path.dirname(Config.SOURCES_CONFIG_PATH) or '.'
    os.makedirs(directory, exist_ok=True)
    encrypted = encrypt_source_secrets(sources)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode='w',
            encoding='utf-8',
            dir=directory,
            prefix='.sources-',
            suffix='.tmp',
            delete=False,
        ) as temp_file:
            temp_path = temp_file.name
            json.dump({'backup_sources': encrypted}, temp_file, indent=2)
            temp_file.flush()
            os.fsync(temp_file.fileno())
        os.chmod(temp_path, 0o600)
        os.replace(temp_path, Config.SOURCES_CONFIG_PATH)
    except Exception:
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)
        raise


def migrate_source_secrets():
    """Encrypt legacy plaintext inline credentials in place once at startup."""
    raw = _read_raw_sources()
    encrypted = encrypt_source_secrets(raw)
    if encrypted == raw:
        return False
    save_sources(raw)
    logger.info('Encrypted legacy inline source credentials')
    return True
