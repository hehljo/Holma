"""
Database Models
"""
from datetime import datetime
from app import db
import json
from app.time_utils import utc_now_naive


class Backup(db.Model):
    """Backup execution record"""
    __tablename__ = 'backups'

    id = db.Column(db.Integer, primary_key=True)
    backup_id = db.Column(db.String(36), unique=True, nullable=False)
    status = db.Column(db.String(20), nullable=False, default='pending')  # pending, running, completed, failed
    started_at = db.Column(db.DateTime, default=utc_now_naive)
    completed_at = db.Column(db.DateTime, nullable=True)
    duration = db.Column(db.Integer, nullable=True)  # seconds
    total_size = db.Column(db.BigInteger, default=0)  # bytes
    sources_count = db.Column(db.Integer, default=0)
    error_message = db.Column(db.Text, nullable=True)
    trigger_type = db.Column(db.String(20), default='manual')  # manual, usb_mount, scheduled

    # Relationships
    source_results = db.relationship('BackupSourceResult', backref='backup', lazy=True, cascade='all, delete-orphan')

    def to_dict(self):
        """Convert to dictionary"""
        return {
            'backup_id': self.backup_id,
            'status': self.status,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'duration': self.duration,
            'total_size': self.total_size,
            'sources_count': self.sources_count,
            'error_message': self.error_message,
            'trigger_type': self.trigger_type,
            'sources': [sr.to_dict() for sr in self.source_results]
        }


class BackupSourceResult(db.Model):
    """Individual source backup result"""
    __tablename__ = 'backup_source_results'

    id = db.Column(db.Integer, primary_key=True)
    backup_id = db.Column(db.Integer, db.ForeignKey('backups.id'), nullable=False)
    source_id = db.Column(db.String(100), nullable=False)
    source_name = db.Column(db.String(200), nullable=False)
    source_type = db.Column(db.String(50), nullable=False)
    status = db.Column(db.String(20), nullable=False, default='pending')
    started_at = db.Column(db.DateTime, default=utc_now_naive)
    completed_at = db.Column(db.DateTime, nullable=True)
    duration = db.Column(db.Integer, nullable=True)
    files_synced = db.Column(db.Integer, default=0)
    size_synced = db.Column(db.BigInteger, default=0)
    progress = db.Column(db.Integer, default=0)  # 0-100
    error_message = db.Column(db.Text, nullable=True)
    logs = db.Column(db.Text, nullable=True)

    def to_dict(self):
        """Convert to dictionary"""
        return {
            'source_id': self.source_id,
            'source_name': self.source_name,
            'source_type': self.source_type,
            'status': self.status,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'duration': self.duration,
            'files_synced': self.files_synced,
            'size_synced': self.size_synced,
            'progress': self.progress,
            'error_message': self.error_message,
            'logs': self.logs
        }


class Setting(db.Model):
    """Key-value settings stored in database"""
    __tablename__ = 'settings'

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False)
    value = db.Column(db.Text, nullable=True)
    updated_at = db.Column(db.DateTime, default=utc_now_naive, onupdate=utc_now_naive)

    @staticmethod
    def get(key, default=None):
        setting = Setting.query.filter_by(key=key).first()
        if not setting:
            return default
        # Decrypt credential values
        if key.startswith('credential.'):
            from app.crypto import decrypt_value
            decrypted = decrypt_value(setting.value)
            return decrypted if decrypted else default
        return setting.value

    @staticmethod
    def set(key, value):
        from app import db as _db
        store_value = value
        # Encrypt credential values
        if key.startswith('credential.'):
            from app.crypto import encrypt_value
            store_value = encrypt_value(value)
        setting = Setting.query.filter_by(key=key).first()
        if setting:
            setting.value = store_value
        else:
            setting = Setting(key=key, value=store_value)
            _db.session.add(setting)
        _db.session.commit()
        return setting

    # Credential keys are stored with prefix 'credential.'
    # e.g. 'credential.github_token', 'credential.supabase_db_password'
    CREDENTIAL_KEYS = [
        'credential.github_token',
        'credential.nas_password_1',
        'credential.supabase_db_password',
        'credential.supabase_service_role_key',
        'credential.smtp_password',
        'credential.telegram_bot_token',
        'credential.rclone_gdrive_token',
    ]


class User(db.Model):
    """User model for authentication"""
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, default=utc_now_naive)
    last_login = db.Column(db.DateTime, nullable=True)

    def to_dict(self):
        """Convert to dictionary"""
        return {
            'id': self.id,
            'username': self.username,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'last_login': self.last_login.isoformat() if self.last_login else None
        }
