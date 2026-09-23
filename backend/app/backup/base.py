"""
Base class for backup handlers
"""
from abc import ABC, abstractmethod
import logging
import os
import re

logger = logging.getLogger(__name__)


class InvalidBackupResult(ValueError):
    """Raised when a handler violates the backup result contract."""


def normalize_backup_result(result):
    """Validate and normalize a handler result without hiding partial errors."""
    if not isinstance(result, dict):
        raise InvalidBackupResult('Backup handler must return a result dictionary')

    normalized = dict(result)
    for field in ('files_synced', 'size_synced'):
        value = normalized.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise InvalidBackupResult(
                f'Backup handler returned invalid {field}: expected non-negative integer'
            )

    logs = normalized.get('logs', '')
    if not isinstance(logs, str):
        raise InvalidBackupResult('Backup handler returned invalid logs: expected string')

    raw_errors = normalized.get('errors', [])
    if isinstance(raw_errors, str):
        raw_errors = [raw_errors]
    if not isinstance(raw_errors, list):
        raise InvalidBackupResult('Backup handler returned invalid errors: expected list')

    errors = [str(error).strip() for error in raw_errors if str(error).strip()]
    for line in logs.splitlines():
        stripped = line.strip()
        if re.match(r'^ERROR(?:\s|:)', stripped, flags=re.IGNORECASE):
            errors.append(stripped)

    # Preserve order while avoiding the same message from explicit errors and logs.
    errors = list(dict.fromkeys(errors))
    status = normalized.get('status', 'completed')
    if status not in ('completed', 'partial', 'failed'):
        raise InvalidBackupResult(f'Backup handler returned invalid status: {status}')

    if errors and status == 'completed':
        has_artifacts = normalized['files_synced'] > 0 or normalized['size_synced'] > 0
        status = 'partial' if has_artifacts else 'failed'
    elif status in ('partial', 'failed') and not errors:
        errors.append(f'Handler reported status {status} without an error message')

    normalized['status'] = status
    normalized['errors'] = errors
    normalized['logs'] = logs
    return normalized


class BackupHandler(ABC):
    """Abstract base class for backup handlers"""

    def __init__(self, source_config, dest_path):
        """
        Initialize backup handler

        Args:
            source_config: Configuration dict for the source
            dest_path: Destination path for backups
        """
        # Flatten: merge config sub-object into top level so handlers
        # can access values directly (e.g. self.source_config.get('host'))
        # regardless of whether the frontend nests them under 'config' or not.
        if 'config' in source_config and isinstance(source_config['config'], dict):
            merged = dict(source_config)
            merged.update(source_config['config'])
            self.source_config = merged
        else:
            self.source_config = source_config
        self.dest_path = dest_path
        self.logs = []
        self._live_log_callback = None  # set by executor for live streaming

    @abstractmethod
    def backup(self):
        """
        Execute backup operation

        Returns:
            dict: {
                'files_synced': int,
                'size_synced': int,
                'logs': str,
                'status': 'completed' | 'partial' | 'failed' (optional),
                'errors': list[str] (optional)
            }
        """
        pass

    def log(self, message):
        """Add a log message"""
        self.logs.append(message)
        logger.info(message)
        if self._live_log_callback:
            try:
                self._live_log_callback(self.get_logs())
            except Exception:
                pass

    def get_logs(self):
        """Get all logs as a string"""
        return '\n'.join(self.logs)

    def _get_directory_size(self, path):
        """Get total size of directory"""
        total_size = 0
        for dirpath, dirnames, filenames in os.walk(path):
            for filename in filenames:
                filepath = os.path.join(dirpath, filename)
                try:
                    total_size += os.path.getsize(filepath)
                except:
                    pass
        return total_size

    def _get_file_size(self, path):
        """Get size of a single file"""
        try:
            return os.path.getsize(path)
        except:
            return 0

    def _as_list(self, value):
        """Normalize UI string/list values to a clean list."""
        if isinstance(value, list):
            return [item for item in value if item]
        if not value:
            return []
        return [item.strip() for item in str(value).split(',') if item.strip()]

    def _get_config_credential(self, field, env_key, required=True):
        """Get credential from flattened source config, credentials object, then env/DB."""
        credentials = self.source_config.get('credentials', {})
        value = self.source_config.get(field) or credentials.get(field)
        if value:
            return value
        credential_env = credentials.get(f'{field}_env') or credentials.get(env_key)
        if credential_env:
            return self._get_env_credential(credential_env, required=required)
        return self._get_env_credential(env_key, required=required)

    def _get_env_credential(self, key, required=True):
        """Get credential: DB (global) first, then environment variable.
        Respects credential_profile from source config for multi-account support."""
        # Map env var names to DB credential keys
        env_to_db = {
            'GITHUB_TOKEN': 'github_token',
            'NAS_PASSWORD_1': 'nas_password_1',
            'SUPABASE_DB_PASSWORD': 'supabase_db_password',
            'SUPABASE_SERVICE_ROLE_KEY': 'supabase_service_role_key',
            'SMTP_PASSWORD': 'smtp_password',
            'TELEGRAM_BOT_TOKEN': 'telegram_bot_token',
            'RCLONE_CONFIG_GDRIVE_TOKEN': 'rclone_gdrive_token',
        }
        db_key = env_to_db.get(key)
        if db_key:
            try:
                from app.api.settings import get_credential
                profile = self.source_config.get('credential_profile')
                value = get_credential(db_key, profile=profile)
                if value:
                    return value
            except Exception:
                pass
        # Fallback to env var
        value = os.environ.get(key, '')
        if required and not value:
            raise Exception(f"Credential not found. Set it in Settings → Credentials or as {key} env var.")
        return value
