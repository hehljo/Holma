"""Validated access to settings that affect live backup execution."""
import logging
import os

from app.config import Config
from app.models.backup import Setting

logger = logging.getLogger(__name__)


def get_setting(key, default=None):
    """Read a DB setting, then its environment fallback, then a default."""
    db_value = Setting.get(key)
    if db_value is not None:
        return db_value
    env_map = {
        'backup_base_path': 'BACKUP_BASE_PATH',
        'max_parallel_tasks': 'MAX_PARALLEL_TASKS',
        'log_retention_days': 'LOG_RETENTION_DAYS',
        'backup_retention_count': 'BACKUP_RETENTION_COUNT',
        'auto_cleanup': 'AUTO_CLEANUP',
    }
    env_key = env_map.get(key)
    if env_key:
        env_value = os.environ.get(env_key)
        if env_value:
            return env_value
    return default


def validate_backup_base_path(value):
    """Restrict UI-selected destinations to the mounted backup root."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError('backup_base_path must be a non-empty absolute path')
    candidate = os.path.realpath(value.strip())
    allowed_root = os.path.realpath(Config.BACKUP_BASE_PATH)
    if not os.path.isabs(value.strip()):
        raise ValueError('backup_base_path must be an absolute path')
    try:
        inside = os.path.commonpath((allowed_root, candidate)) == allowed_root
    except ValueError:
        inside = False
    if not inside:
        raise ValueError(
            f'backup_base_path must stay inside {Config.BACKUP_BASE_PATH}'
        )
    return candidate


def backup_root_path():
    """Return the effective safe backup root used by all live operations."""
    configured = get_setting('backup_base_path', Config.BACKUP_BASE_PATH)
    try:
        return validate_backup_base_path(configured)
    except ValueError:
        logger.error('Ignoring unsafe stored backup_base_path')
        return os.path.realpath(Config.BACKUP_BASE_PATH)
