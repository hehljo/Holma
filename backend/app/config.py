"""
Configuration Module
"""
import os
from datetime import timedelta


def _get_int_env(name, default):
    value = os.environ.get(name, default)
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


class Config:
    """Base configuration"""

    # Flask
    SECRET_KEY = os.environ.get('SECRET_KEY', '')
    DEBUG = os.environ.get('DEBUG', 'false').lower() == 'true'
    FORCE_HTTPS = os.environ.get('FORCE_HTTPS', 'false').lower() == 'true'
    TRUST_PROXY_HEADERS = os.environ.get(
        'TRUST_PROXY_HEADERS', 'false'
    ).lower() == 'true'

    @classmethod
    def validate(cls):
        """Validate critical configuration at startup"""
        insecure_values = {
            'dev-secret-key-change-in-production',
            'CHANGE_ME',
            'CHANGE_THIS_TO_A_RANDOM_SECRET_KEY',
        }
        if cls.SECRET_KEY in insecure_values or len(cls.SECRET_KEY) < 32:
            raise RuntimeError(
                "FATAL: SECRET_KEY must be a random value of at least 32 characters. "
                "Generate one with: python -c \"import secrets; print(secrets.token_urlsafe(32))\""
            )
        if len(cls.JWT_SECRET_KEY) < 32:
            raise RuntimeError('FATAL: JWT_SECRET_KEY must be at least 32 characters')

    # Database
    DATABASE_URL = os.environ.get('DATABASE_URL', 'sqlite:////data/backupgenie.db')
    SQLALCHEMY_DATABASE_URI = DATABASE_URL
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    APP_INIT_LOCK_PATH = os.environ.get(
        'APP_INIT_LOCK_PATH', '/data/.backupgenie-init.lock'
    )
    SETUP_TOKEN_PATH = os.environ.get(
        'SETUP_TOKEN_PATH', '/data/.holma-setup-token'
    )

    # Backup Configuration
    BACKUP_BASE_PATH = os.environ.get('BACKUP_BASE_PATH', '/mnt/backup')
    MAX_PARALLEL_TASKS = _get_int_env('MAX_PARALLEL_TASKS', 2)
    LOG_RETENTION_DAYS = _get_int_env('LOG_RETENTION_DAYS', 30)
    JOB_LOCK_PATH = os.environ.get(
        'JOB_LOCK_PATH', '/data/.backupgenie-job.lock'
    )
    RESTORE_JOB_PATH = os.environ.get(
        'RESTORE_JOB_PATH', '/data/restore-jobs'
    )
    RESTORE_JOB_LOCK_PATH = os.environ.get(
        'RESTORE_JOB_LOCK_PATH', '/data/.backupgenie-restore-job.lock'
    )
    DOCKER_HELPER_IMAGE = os.environ.get(
        'DOCKER_HELPER_IMAGE', 'alpine:3.24.1'
    )

    # API Configuration
    API_PORT = _get_int_env('API_PORT', 5000)
    # The container must listen on its network interface; the published port
    # and reverse proxy control external exposure.
    API_HOST = os.environ.get('API_HOST', '0.0.0.0')  # nosec B104

    # JWT Configuration
    JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY', SECRET_KEY)
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=24)

    # Sources Configuration
    SOURCES_CONFIG_PATH = os.environ.get('SOURCES_CONFIG_PATH', '/app/config/sources.json')
    RCLONE_CONFIG_PATH = os.environ.get('RCLONE_CONFIG_PATH', '/app/config/rclone.conf')

    # Logging
    LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')
    LOG_FILE = os.environ.get('LOG_FILE', '/var/log/backupgenie/app.log')
