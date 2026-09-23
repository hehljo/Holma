"""
Settings API Endpoints
Provides system configuration and management
All settings are persisted in the database.
"""
from flask import Blueprint, request, jsonify
import logging
import shutil
import os
import re
import subprocess

import requests

from app import db, limiter
from app.api.auth import admin_required
from app.config import Config
from app.models.backup import Setting
from app.runtime_settings import (
    backup_root_path,
    get_setting,
    validate_backup_base_path,
)

logger = logging.getLogger(__name__)

settings_bp = Blueprint('settings', __name__)

# Settings that can be configured via UI
CONFIGURABLE_SETTINGS = {
    'backup_base_path': {'type': 'string', 'default': '/mnt/backup'},
    'max_parallel_tasks': {'type': 'int', 'default': 2, 'min': 1, 'max': 10},
    'log_retention_days': {'type': 'int', 'default': 30, 'min': 1},
    'backup_retention_count': {'type': 'int', 'default': 10, 'min': 1, 'max': 1000},
    'auto_cleanup': {'type': 'bool', 'default': True},
}

PROFILE_NAME_RE = re.compile(r'^[a-z0-9][a-z0-9_-]{0,49}$')


def normalize_settings(values):
    """Validate a settings payload completely before anything is persisted."""
    if not isinstance(values, dict):
        raise ValueError('Settings must be an object')

    normalized = {}
    for key, meta in CONFIGURABLE_SETTINGS.items():
        if key not in values:
            continue
        value = values[key]
        if meta['type'] == 'int':
            try:
                value = int(value)
            except (ValueError, TypeError) as exc:
                raise ValueError(f'{key} must be a number') from exc
            if 'min' in meta and value < meta['min']:
                raise ValueError(f'{key} must be at least {meta["min"]}')
            if 'max' in meta and value > meta['max']:
                raise ValueError(f'{key} must be at most {meta["max"]}')
        elif meta['type'] == 'bool':
            if isinstance(value, bool):
                pass
            elif str(value).lower() in ('true', '1', 'yes', 'on'):
                value = True
            elif str(value).lower() in ('false', '0', 'no', 'off'):
                value = False
            else:
                raise ValueError(f'{key} must be a boolean')
        elif key == 'backup_base_path':
            value = validate_backup_base_path(value)
        normalized[key] = str(value)
    return normalized


def stage_settings(normalized):
    """Stage validated settings in the current DB transaction."""
    for key, value in normalized.items():
        setting = Setting.query.filter_by(key=key).first()
        if setting:
            setting.value = value
        else:
            db.session.add(Setting(key=key, value=value))


def apply_runtime_settings(normalized):
    """Apply settings that affect already-created process resources."""
    if 'log_retention_days' in normalized:
        from logging.handlers import TimedRotatingFileHandler
        for handler in logging.getLogger().handlers:
            if isinstance(handler, TimedRotatingFileHandler):
                handler.backupCount = int(normalized['log_retention_days'])


def _store_credentials_atomic(values):
    """Encrypt and stage credential key/value pairs in one transaction."""
    from app.crypto import encrypt_value

    for key, value in values.items():
        setting = Setting.query.filter_by(key=key).first()
        encrypted = encrypt_value(value)
        if setting:
            setting.value = encrypted
        else:
            db.session.add(Setting(key=key, value=encrypted))
    db.session.commit()


def get_credential(name, profile=None):
    """Get credential from DB, fall back to env var.

    Args:
        name: Legacy credential key (e.g. 'github_token') or provider.field (e.g. 'github.token')
        profile: Optional profile name. If None, returns first available.
    """
    # Resolve provider-based key: convert legacy names to provider.field
    legacy_to_provider = {}
    for provider, meta in CREDENTIAL_PROVIDERS.items():
        for field, legacy_key in meta['legacy_map'].items():
            legacy_to_provider[legacy_key] = f'{provider}.{field}'

    provider_key = legacy_to_provider.get(name, name)

    if profile:
        db_val = Setting.get(f'credential.{provider_key}.{profile}')
        if db_val:
            return db_val
    else:
        # Try legacy single-key format (backward compat)
        db_val = Setting.get(f'credential.{name}')
        if db_val:
            return db_val
        # Try provider-based keys
        db_val = Setting.get(f'credential.{provider_key}')
        if db_val:
            return db_val
        # Try first available profile
        all_settings = Setting.query.filter(
            Setting.key.like(f'credential.{provider_key}.%')
        ).first()
        if all_settings:
            from app.crypto import decrypt_value
            decrypted = decrypt_value(all_settings.value)
            if decrypted:
                return decrypted

    # Env fallback
    env_map = {
        'github_token': 'GITHUB_TOKEN',
        'nas_password_1': 'NAS_PASSWORD_1',
        'supabase_db_password': 'SUPABASE_DB_PASSWORD',
        'supabase_service_role_key': 'SUPABASE_SERVICE_ROLE_KEY',
        'smtp_password': 'SMTP_PASSWORD',
        'telegram_bot_token': 'TELEGRAM_BOT_TOKEN',
        'rclone_gdrive_token': 'RCLONE_CONFIG_GDRIVE_TOKEN',
    }
    env_key = env_map.get(name)
    if env_key:
        return os.environ.get(env_key, '')
    return ''


def get_provider_profiles(provider):
    """Get all profiles for a provider (e.g. 'supabase').

    Returns:
        list of dicts with profile name and which fields are configured.
    """
    meta = CREDENTIAL_PROVIDERS.get(provider)
    if not meta:
        return []

    # Collect all profile names from DB
    profile_names = set()
    for field in meta['fields']:
        key_prefix = f'credential.{provider}.{field}.'
        settings = Setting.query.filter(Setting.key.like(key_prefix + '%')).all()
        for s in settings:
            profile_name = s.key.split(key_prefix, 1)[1]
            profile_names.add(profile_name)

    # Check legacy single-key entries
    has_legacy = False
    for field, legacy_key in meta['legacy_map'].items():
        if Setting.query.filter_by(key=f'credential.{legacy_key}').first():
            has_legacy = True
            break

    profiles = []
    if has_legacy:
        fields_status = {}
        for field, legacy_key in meta['legacy_map'].items():
            fields_status[field] = bool(Setting.get(f'credential.{legacy_key}'))
        profiles.append({
            'profile': 'default',
            'source': 'database',
            'fields': fields_status
        })

    for pname in sorted(profile_names):
        fields_status = {}
        for field in meta['fields']:
            val = Setting.get(f'credential.{provider}.{field}.{pname}')
            fields_status[field] = bool(val)
        profiles.append({
            'profile': pname,
            'source': 'database',
            'fields': fields_status
        })

    # Env fallback
    if not profiles:
        has_env = False
        fields_status = {}
        for field, env_key in meta['env_map'].items():
            val = os.environ.get(env_key, '')
            fields_status[field] = bool(val)
            if val:
                has_env = True
        if has_env:
            profiles.append({
                'profile': 'default',
                'source': 'environment',
                'fields': fields_status
            })

    return profiles


@settings_bp.route('', methods=['GET'])
@admin_required
def get_settings(current_user):
    """Get current system settings with real storage stats"""
    backup_path = backup_root_path()

    try:
        stat = shutil.disk_usage(backup_path)
        storage = {
            'total_bytes': stat.total,
            'used_bytes': stat.used,
            'free_bytes': stat.free,
            'percentage_used': round((stat.used / stat.total) * 100, 2) if stat.total > 0 else 0
        }
    except Exception as e:
        storage = {
            'total_bytes': 0,
            'used_bytes': 0,
            'free_bytes': 0,
            'percentage_used': 0,
            'error': str(e)
        }

    settings = {
        'backup_base_path': backup_path,
        'max_parallel_tasks': int(get_setting('max_parallel_tasks', 2)),
        'log_retention_days': int(get_setting('log_retention_days', 30)),
        'backup_retention_count': int(get_setting('backup_retention_count', 10)),
        'api_auth_enabled': True,
        'https_only': os.getenv('FORCE_HTTPS', 'false').lower() == 'true',
        'auto_cleanup': str(get_setting('auto_cleanup', 'true')).lower() == 'true',
        'storage': storage
    }

    return jsonify(settings), 200


@settings_bp.route('', methods=['PUT'])
@admin_required
def update_settings(current_user):
    """Update system settings - persisted in database"""
    data = request.get_json()

    if not isinstance(data, dict) or not data:
        return jsonify({'error': 'No data provided'}), 400

    try:
        normalized = normalize_settings(data)
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400

    try:
        stage_settings(normalized)
        db.session.commit()
    except Exception:
        db.session.rollback()
        logger.exception('Settings update failed')
        return jsonify({'error': 'Settings update failed'}), 500

    apply_runtime_settings(normalized)

    return jsonify({
        'message': 'Settings updated successfully',
        'updated': list(normalized)
    }), 200


# --- Global Credentials ---

# Credential providers with their fields
CREDENTIAL_PROVIDERS = {
    'github': {
        'fields': ['token'],
        'legacy_map': {'token': 'github_token'},
        'env_map': {'token': 'GITHUB_TOKEN'},
    },
    'nas': {
        'fields': ['password'],
        'legacy_map': {'password': 'nas_password_1'},
        'env_map': {'password': 'NAS_PASSWORD_1'},
    },
    'supabase': {
        'fields': ['connection_string', 'db_password', 'service_role_key'],
        'legacy_map': {'connection_string': 'supabase_connection_string', 'db_password': 'supabase_db_password', 'service_role_key': 'supabase_service_role_key'},
        'env_map': {'connection_string': 'SUPABASE_CONNECTION_STRING', 'db_password': 'SUPABASE_DB_PASSWORD', 'service_role_key': 'SUPABASE_SERVICE_ROLE_KEY'},
    },
    'smtp': {
        'fields': ['password'],
        'legacy_map': {'password': 'smtp_password'},
        'env_map': {'password': 'SMTP_PASSWORD'},
    },
    'telegram': {
        'fields': ['bot_token'],
        'legacy_map': {'bot_token': 'telegram_bot_token'},
        'env_map': {'bot_token': 'TELEGRAM_BOT_TOKEN'},
    },
    'gdrive': {
        'fields': ['token'],
        'legacy_map': {'token': 'rclone_gdrive_token'},
        'env_map': {'token': 'RCLONE_CONFIG_GDRIVE_TOKEN'},
    },
}

# Flat list for backward compat
CREDENTIAL_TYPES = [
    'github_token', 'nas_password_1',
    'supabase_db_password', 'supabase_service_role_key',
    'smtp_password', 'telegram_bot_token', 'rclone_gdrive_token'
]


@settings_bp.route('/credentials', methods=['GET'])
@admin_required
def get_credentials(current_user):
    """Get all credential providers with their profiles (never returns actual values)"""
    credentials = {}
    for provider, meta in CREDENTIAL_PROVIDERS.items():
        profiles = get_provider_profiles(provider)
        credentials[provider] = {
            'fields': meta['fields'],
            'profiles': profiles,
            'configured': len(profiles) > 0
        }

    return jsonify(credentials), 200


@settings_bp.route('/credentials', methods=['PUT'])
@admin_required
def update_credentials(current_user):
    """Legacy: Update credentials with flat key-value format"""
    data = request.get_json()

    if not isinstance(data, dict) or not data:
        return jsonify({'error': 'No data provided'}), 400

    pending = {}
    updated = []
    for key, value in data.items():
        if key not in CREDENTIAL_TYPES:
            continue
        if isinstance(value, str) and value.strip():
            pending[f'credential.{key}'] = value.strip()
            updated.append(key)

    try:
        _store_credentials_atomic(pending)
    except Exception:
        db.session.rollback()
        logger.exception('Credential update failed')
        return jsonify({'error': 'Credentials could not be saved'}), 500

    return jsonify({
        'message': 'Credentials updated',
        'updated': updated
    }), 200


@settings_bp.route('/credentials/profile', methods=['POST'])
@admin_required
def add_credential_profile(current_user):
    """Add or update a credential profile for a provider"""
    data = request.get_json() or {}
    provider = data.get('provider', '').strip()
    profile = data.get('profile', '').strip()
    values = data.get('values', {})

    if not provider or provider not in CREDENTIAL_PROVIDERS:
        return jsonify({'error': 'Invalid provider'}), 400
    if not profile:
        return jsonify({'error': 'Profile name is required'}), 400
    if not isinstance(values, dict) or not values:
        return jsonify({'error': 'At least one field value is required'}), 400

    meta = CREDENTIAL_PROVIDERS[provider]

    profile = profile.lower().replace(' ', '_')
    if not PROFILE_NAME_RE.fullmatch(profile):
        return jsonify({
            'error': 'Profile name may only contain letters, numbers, _ and -'
        }), 400

    pending = {}
    saved_fields = []
    for field, value in values.items():
        if field not in meta['fields']:
            continue
        if isinstance(value, str) and value.strip():
            pending[f'credential.{provider}.{field}.{profile}'] = value.strip()
            saved_fields.append(field)

    if not saved_fields:
        return jsonify({'error': 'No valid fields provided'}), 400

    try:
        _store_credentials_atomic(pending)
    except Exception:
        db.session.rollback()
        logger.exception('Credential profile update failed')
        return jsonify({'error': 'Credential profile could not be saved'}), 500

    return jsonify({
        'message': f'Profile "{profile}" saved for {provider}',
        'profile': profile,
        'fields': saved_fields
    }), 200


def _test_github_token(token):
    """Verify a GitHub token and report the account and granted scopes."""
    resp = requests.get(
        'https://api.github.com/user',
        headers={
            'Authorization': f'token {token}',
            'Accept': 'application/vnd.github.v3+json',
        },
        timeout=15,
    )

    if resp.status_code == 401:
        return False, 'Token is invalid or expired'
    if resp.status_code == 403:
        if resp.headers.get('X-RateLimit-Remaining') == '0':
            return False, 'GitHub rate limit reached, try again later'
        return False, 'Token lacks the required permissions'
    resp.raise_for_status()

    login = resp.json().get('login', '?')
    scopes = resp.headers.get('X-OAuth-Scopes', '')
    scope_list = [s.strip() for s in scopes.split(',') if s.strip()]

    # Classic tokens report scopes; fine-grained tokens report none, so a
    # missing 'repo' scope is only a warning when scopes are present at all.
    if scope_list and not any(s in scope_list for s in ('repo', 'public_repo')):
        return False, (f'Connected as {login}, but the token is missing the '
                       f'"repo" scope needed for backups')

    detail = f' (scopes: {", ".join(scope_list)})' if scope_list else ''
    return True, f'Connected as {login}{detail}'


def _test_telegram_token(token):
    """Verify a Telegram bot token."""
    resp = requests.get(f'https://api.telegram.org/bot{token}/getMe', timeout=15)
    if resp.status_code == 401:
        return False, 'Bot token is invalid'
    resp.raise_for_status()
    data = resp.json()
    if not data.get('ok'):
        return False, data.get('description', 'Telegram rejected the token')
    return True, f"Connected as @{data.get('result', {}).get('username', '?')}"


@settings_bp.route('/credentials/test', methods=['POST'])
@admin_required
@limiter.limit("20 per hour")
def test_credential(current_user):
    """Test a stored credential against the provider's API.

    Tests the saved credential, so the token never has to be sent from the
    browser just to check whether it still works.
    """
    data = request.get_json() or {}
    provider = (data.get('provider') or '').strip()
    profile = (data.get('profile') or '').strip() or None

    if provider not in CREDENTIAL_PROVIDERS:
        return jsonify({'error': 'Invalid provider'}), 400

    testable = {
        'github': ('token', _test_github_token),
        'telegram': ('bot_token', _test_telegram_token),
    }
    if provider not in testable:
        return jsonify({
            'error': f'Testing is not supported for {provider} yet'
        }), 400

    field, test_func = testable[provider]
    credential = get_credential(f'{provider}.{field}', profile=profile)
    if not credential:
        return jsonify({'error': 'No credential stored for this profile'}), 404

    try:
        success, message = test_func(credential)
    except requests.Timeout:
        return jsonify({'success': False, 'message': 'Connection timed out'}), 200
    except requests.HTTPError as e:
        # Never log the exception object: its text contains the request URL,
        # and Telegram carries the bot token inside that URL.
        status = e.response.status_code if e.response is not None else 'unknown'
        logger.error('Credential test failed for %s: HTTP %s', provider, status)
        return jsonify({
            'success': False,
            'message': 'The provider returned an error'
        }), 200
    except requests.RequestException as e:
        logger.error(
            'Credential test network error for %s: %s', provider, type(e).__name__
        )
        return jsonify({
            'success': False,
            'message': 'Could not reach the provider'
        }), 200

    return jsonify({'success': success, 'message': message}), 200


@settings_bp.route('/credentials/profile', methods=['DELETE'])
@admin_required
def delete_credential_profile(current_user):
    """Delete a credential profile (all fields)"""
    data = request.get_json() or {}
    provider = data.get('provider', '').strip()
    profile = data.get('profile', '').strip()

    if not provider or provider not in CREDENTIAL_PROVIDERS:
        return jsonify({'error': 'Invalid provider'}), 400
    if not profile:
        return jsonify({'error': 'Profile name is required'}), 400
    if not PROFILE_NAME_RE.fullmatch(profile):
        return jsonify({'error': 'Invalid profile name'}), 400

    meta = CREDENTIAL_PROVIDERS[provider]
    deleted = 0

    # Delete all fields for this profile
    for field in meta['fields']:
        key = f'credential.{provider}.{field}.{profile}'
        setting = Setting.query.filter_by(key=key).first()
        if setting:
            db.session.delete(setting)
            deleted += 1

    # Also check legacy keys if profile is 'default'
    if profile == 'default':
        for field, legacy_key in meta['legacy_map'].items():
            setting = Setting.query.filter_by(key=f'credential.{legacy_key}').first()
            if setting:
                db.session.delete(setting)
                deleted += 1

    if deleted == 0:
        return jsonify({'error': 'Profile not found'}), 404

    db.session.commit()
    return jsonify({'message': f'Profile "{profile}" deleted ({deleted} fields)'}), 200


# --- System Logs ---

@settings_bp.route('/logs', methods=['GET'])
@admin_required
def get_logs(current_user):
    """Get system log file contents"""
    lines = request.args.get('lines', 200, type=int)
    lines = min(lines, 2000)  # Cap at 2000

    log_file = Config.LOG_FILE
    if not os.path.isfile(log_file):
        return jsonify({'logs': '', 'lines': 0, 'file': log_file}), 200

    try:
        # Use tail for efficient reading of last N lines
        result = subprocess.run(
            ['tail', '-n', str(lines), log_file],
            capture_output=True, text=True, timeout=5
        )
        content = result.stdout
        line_count = content.count('\n')
        return jsonify({
            'logs': content,
            'lines': line_count,
            'file': log_file
        }), 200
    except Exception as e:
        return jsonify({'error': f'Failed to read logs: {str(e)}'}), 500


@settings_bp.route('/logs/clear', methods=['POST'])
@admin_required
def clear_logs(current_user):
    """Clear the log file"""
    log_file = Config.LOG_FILE
    if os.path.isfile(log_file):
        try:
            with open(log_file, 'w') as f:
                f.write('')
            return jsonify({'message': 'Logs cleared'}), 200
        except Exception as e:
            return jsonify({'error': f'Failed to clear logs: {str(e)}'}), 500
    return jsonify({'message': 'No log file found'}), 200
