"""
Backup Executor
Coordinates backup operations across multiple sources
"""
import logging
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import os
import shutil

from app import db
from app.models.backup import Backup, BackupSourceResult, Setting
from app.config import Config
from app.backup.paths import source_backup_path, validate_source_id
from app.backup.base import normalize_backup_result
from app.time_utils import utc_now_naive
from app.runtime_settings import backup_root_path
from app.backup.sources.smb import SMBBackup
from app.backup.sources.github import GitHubBackup
from app.backup.artifacts import (
    DEFAULT_BACKUP_RETENTION_COUNT, TIMESTAMP_FORMAT, RunArtifact, select_expired,
)
from app.backup.sources.rclone import RcloneBackup
from app.backup.sources.local import LocalBackup
from app.backup.sources.git import (
    GitLabBackup, GiteaBackup, ForgejoBackup,
    BitbucketBackup, CodebergBackup
)
from app.backup.sources.database import (
    MySQLBackup, PostgreSQLBackup, MongoDBBackup,
    RedisBackup, SQLiteBackup, CouchDBBackup, InfluxDBBackup
)
from app.backup.sources.ftp import FTPBackup, SFTPBackup
from app.backup.sources.webdav import WebDAVBackup
from app.backup.sources.docker import DockerVolumeBackup, DockerImageBackup
from app.backup.sources.rsync_ssh import RsyncSSHBackup
from app.backup.sources.selfhosted import SelfHostedBackup
from app.backup.sources.proxmox import ProxmoxBackup
from app.backup.sources.supabase import SupabaseBackup
from app.notifications.manager import NotificationManager

logger = logging.getLogger(__name__)


class BackupExecutor:
    """Executes backup operations"""

    # Class-level dictionary to track running backups
    _running_backups = {}

    def __init__(self, backup_id, enable_notifications=True, app=None):
        self.backup_id = backup_id
        self.app = app
        self.backup_base_path = Config.BACKUP_BASE_PATH
        self.enable_notifications = enable_notifications
        self.notification_manager = NotificationManager() if enable_notifications else None
        self.stop_requested = False

        # Source type handlers
        self.handlers = {
            # Network Storage
            'smb': SMBBackup,
            'nfs': SMBBackup,  # Backward compatibility for custom privileged images
            'local': LocalBackup,

            # Git Platforms
            'github': GitHubBackup,
            'gitlab': GitLabBackup,
            'gitea': GiteaBackup,
            'forgejo': ForgejoBackup,
            'bitbucket': BitbucketBackup,
            'codeberg': CodebergBackup,
            'gitbucket': GiteaBackup,  # GitBucket uses similar API to Gitea

            # Cloud Storage
            'rclone': RcloneBackup,
            'gdrive': RcloneBackup,
            'onedrive': RcloneBackup,
            'dropbox': RcloneBackup,
            's3': RcloneBackup,
            'b2': RcloneBackup,
            'icloud': RcloneBackup,
            'box': RcloneBackup,
            'mega': RcloneBackup,
            'pcloud': RcloneBackup,
            'webdav': WebDAVBackup,

            # Databases
            'mysql': MySQLBackup,
            'mariadb': MySQLBackup,  # MariaDB uses MySQL handler
            'postgresql': PostgreSQLBackup,
            'postgres': PostgreSQLBackup,  # Alias
            'mongodb': MongoDBBackup,
            'mongo': MongoDBBackup,  # Alias
            'redis': RedisBackup,
            'sqlite': SQLiteBackup,
            'couchdb': CouchDBBackup,
            'influxdb': InfluxDBBackup,

            # FTP/SFTP
            'ftp': FTPBackup,
            'ftps': FTPBackup,
            'sftp': SFTPBackup,

            # Docker
            'docker-volume': DockerVolumeBackup,
            'docker-image': DockerImageBackup,

            # Rsync/NAS
            'rsync-ssh': RsyncSSHBackup,
            'rsync': RsyncSSHBackup,  # Alias
            'nas': SMBBackup,  # UI label is NAS (SMB/CIFS)

            # Proxmox VE
            'proxmox': ProxmoxBackup,
            'proxmox-ve': ProxmoxBackup,  # Alias

            # Self-Hosted Services - Media Servers
            'plex': SelfHostedBackup,
            'jellyfin': SelfHostedBackup,
            'immich': SelfHostedBackup,
            'photoprism': SelfHostedBackup,
            'komga': SelfHostedBackup,
            'kaleidescape': SelfHostedBackup,
            'musicbrainz': SelfHostedBackup,

            # Self-Hosted Services - File Storage
            'seafile': SelfHostedBackup,

            # Self-Hosted Services - Smart Home & Automation
            'homeassistant': SelfHostedBackup,
            'grafana': SelfHostedBackup,
            'nodered': SelfHostedBackup,
            'prometheus': SelfHostedBackup,
            'loki': SelfHostedBackup,

            # Self-Hosted Services - Security & Password Management
            'vaultwarden': SelfHostedBackup,
            'bitwarden': SelfHostedBackup,

            # Self-Hosted Services - Documentation & Wiki
            'mediawiki': SelfHostedBackup,
            'tiddlywiki': SelfHostedBackup,
            'obsidian': SelfHostedBackup,

            # Self-Hosted Services - Monitoring & Analytics
            'sentry': SelfHostedBackup,

            # Self-Hosted Services - Email & Communication
            'mailcow': SelfHostedBackup,
            'mastodon': SelfHostedBackup,
            'mattermost': SelfHostedBackup,

            # Self-Hosted Services - Content Management
            'paperless-ngx': SelfHostedBackup,
            'archivebox': SelfHostedBackup,
            'wallabag': SelfHostedBackup,
            'linkding': SelfHostedBackup,

            # Self-Hosted Services - Admin & User Management
            'portainer': SelfHostedBackup,
            'yacht': SelfHostedBackup,

            # Self-Hosted Services - Specialized
            'syncthing': SelfHostedBackup,
            'restic': SelfHostedBackup,

            # Cloud Platforms
            'supabase': SupabaseBackup,
        }

    def load_sources(self):
        """Load backup sources from configuration"""
        from app.source_config import load_sources
        return load_sources()

    @classmethod
    def stop_backup(cls, backup_id):
        """Request a backup to stop"""
        executor = cls._running_backups.get(backup_id)
        if executor:
            executor.stop_requested = True
            logger.info(f"Stop requested for backup {backup_id}")
            return True
        return False

    def _application(self):
        """Return the owning Flask app without creating one per source thread."""
        if self.app is None:
            from app import create_app
            self.app = create_app()
        return self.app

    def _stop_is_requested(self):
        """Read the durable stop flag, with the local flag as a fast path."""
        if self.stop_requested:
            return True
        db.session.expire_all()
        backup = Backup.query.filter_by(backup_id=self.backup_id).first()
        if backup and backup.status == 'cancelling':
            self.stop_requested = True
        return self.stop_requested

    @staticmethod
    def _terminal_status(source_results):
        statuses = [result.status for result in source_results]
        if statuses and all(status == 'completed' for status in statuses):
            return 'completed'
        if any(status in ('completed', 'partial') for status in statuses):
            return 'partial'
        return 'failed'

    def execute(self, source_ids=None, parallel=2):
        """Execute a previously reserved backup job."""
        with self._application().app_context():
            backup = Backup.query.filter_by(backup_id=self.backup_id).first()
            if not backup:
                logger.error(f"Backup {self.backup_id} not found")
                return
            if backup.status not in ('pending', 'running', 'cancelling'):
                logger.info(
                    'Backup %s is already terminal (%s)', self.backup_id, backup.status
                )
                return

            # Register this executor
            BackupExecutor._running_backups[self.backup_id] = self
            self.backup_base_path = backup_root_path()

            if backup.status == 'pending':
                backup.status = 'running'
            db.session.commit()

            # The durable source-result rows are the authoritative job payload.
            reserved_results = BackupSourceResult.query.filter_by(
                backup_id=backup.id
            ).order_by(BackupSourceResult.id.asc()).all()
            reserved_ids = [result.source_id for result in reserved_results]
            if source_ids:
                requested = set(source_ids)
                reserved_ids = [source_id for source_id in reserved_ids if source_id in requested]

            all_sources = self.load_sources()
            source_by_id = {source.get('id'): source for source in all_sources}
            sources_to_backup = []
            now = utc_now_naive()
            for source_id in reserved_ids:
                source = source_by_id.get(source_id)
                if source is not None:
                    sources_to_backup.append(source)
                    continue
                result = next(
                    row for row in reserved_results if row.source_id == source_id
                )
                result.status = 'failed'
                result.completed_at = now
                result.duration = int((now - result.started_at).total_seconds())
                result.error_message = 'Source configuration no longer exists'
                result.logs = 'ERROR: Source configuration no longer exists'
                result.progress = 100

            # Sort by priority
            sources_to_backup.sort(key=lambda x: x.get('priority', 999))

            backup.sources_count = len(reserved_results)
            db.session.commit()

            logger.info(
                'Starting backup %s with %d reserved source(s)',
                self.backup_id, len(reserved_results),
            )

            # Send notification: Backup started
            if self.notification_manager:
                try:
                    self.notification_manager.notify_backup_started(
                        self.backup_id, len(reserved_results)
                    )
                except Exception as e:
                    logger.error(f"Failed to send backup started notification: {e}")

            try:
                if self._stop_is_requested():
                    logger.info('Backup %s was cancelled before execution', self.backup_id)
                elif parallel > 1 and len(sources_to_backup) > 1:
                    # Parallel execution
                    executor = ThreadPoolExecutor(max_workers=parallel)
                    futures = {
                        executor.submit(self._backup_source, source): source
                        for source in sources_to_backup
                    }
                    try:
                        for future in as_completed(futures):
                            source = futures[future]
                            try:
                                future.result()
                            except Exception as e:
                                logger.error(f"Error backing up {source.get('id')}: {e}")

                            if self._stop_is_requested():
                                logger.info(f"Backup {self.backup_id} stop requested, cancelling...")
                                for pending in futures:
                                    pending.cancel()
                                break
                    finally:
                        executor.shutdown(
                            wait=True,
                            cancel_futures=self.stop_requested,
                        )
                else:
                    # Sequential execution
                    for source in sources_to_backup:
                        if self._stop_is_requested():
                            logger.info(f"Backup {self.backup_id} stop requested, stopping...")
                            break

                        try:
                            self._backup_source(source)
                        except Exception as e:
                            logger.error(f"Error backing up {source.get('id')}: {e}")

                db.session.expire_all()
                backup = Backup.query.filter_by(backup_id=self.backup_id).first()
                stopped = self._stop_is_requested()
                backup.completed_at = utc_now_naive()
                backup.duration = int((backup.completed_at - backup.started_at).total_seconds())
                results = BackupSourceResult.query.filter_by(backup_id=backup.id).all()

                if stopped:
                    for result in results:
                        if result.status == 'pending':
                            result.status = 'cancelled'
                            result.completed_at = backup.completed_at
                            result.duration = int(
                                (result.completed_at - result.started_at).total_seconds()
                            )
                            result.error_message = 'Cancelled before execution'
                    backup.total_size = sum(result.size_synced or 0 for result in results)
                    backup.status = 'cancelled'
                    logger.info(f"Backup {self.backup_id} cancelled by user")
                else:
                    for result in results:
                        if result.status in ('pending', 'running'):
                            result.status = 'failed'
                            result.completed_at = backup.completed_at
                            result.duration = int(
                                (result.completed_at - result.started_at).total_seconds()
                            )
                            result.error_message = 'Source execution ended without a result'
                    backup.total_size = sum(result.size_synced or 0 for result in results)
                    backup.status = self._terminal_status(results)
                    failed_names = [
                        result.source_name for result in results
                        if result.status in ('failed', 'partial')
                    ]
                    backup.error_message = (
                        f"Source failures: {', '.join(failed_names)}"
                        if failed_names else None
                    )
                    logger.info(
                        'Backup %s finished with status %s',
                        self.backup_id, backup.status,
                    )

                db.session.commit()

                # Send notification: Backup completed, partial, or cancelled
                if self.notification_manager and not stopped:
                    try:
                        if backup.status == 'completed':
                            self.notification_manager.notify_backup_completed(
                                self.backup_id,
                                backup.duration,
                                backup.total_size,
                                len(results),
                            )
                        elif backup.status == 'partial':
                            self.notification_manager.notify_backup_partial(
                                self.backup_id,
                                failed_names,
                                len(results),
                            )
                        else:
                            self.notification_manager.notify_backup_failed(
                                self.backup_id,
                                backup.error_message or 'All sources failed',
                            )
                    except Exception as e:
                        logger.error(f"Failed to send backup completion notification: {e}")

            except Exception as e:
                logger.error(f"Backup {self.backup_id} failed: {e}")
                db.session.rollback()
                backup = Backup.query.filter_by(backup_id=self.backup_id).first()
                backup.status = 'failed'
                backup.error_message = str(e)
                backup.completed_at = utc_now_naive()
                backup.duration = int((backup.completed_at - backup.started_at).total_seconds())
                for result in BackupSourceResult.query.filter_by(backup_id=backup.id).all():
                    if result.status in ('pending', 'running'):
                        result.status = 'failed'
                        result.completed_at = backup.completed_at
                        result.duration = int(
                            (result.completed_at - result.started_at).total_seconds()
                        )
                        result.error_message = 'Backup executor failed before completion'
                db.session.commit()

                # Send notification: Backup failed
                if self.notification_manager:
                    try:
                        self.notification_manager.notify_backup_failed(self.backup_id, str(e))
                    except Exception as ne:
                        logger.error(f"Failed to send backup failure notification: {ne}")

            finally:
                # Unregister this executor
                BackupExecutor._running_backups.pop(self.backup_id, None)

    def _backup_source(self, source):
        """Backup a single source"""
        with self._application().app_context():
            source_id = source.get('id')
            source_type = source.get('type')

            logger.info(f"Backing up source: {source_id} ({source_type})")

            backup = Backup.query.filter_by(backup_id=self.backup_id).first()
            if not backup:
                raise RuntimeError(f'Backup {self.backup_id} not found')
            result = BackupSourceResult.query.filter_by(
                backup_id=backup.id,
                source_id=source_id,
            ).first()
            if not result:
                raise RuntimeError(f'Source {source_id} was not reserved for this backup')
            if result.status != 'pending':
                raise RuntimeError(
                    f'Source {source_id} cannot start from status {result.status}'
                )
            result.status = 'running'
            result.started_at = utc_now_naive()
            db.session.commit()

            # Local, not on self: sources run in parallel threads and share
            # this executor instance.
            retention_ran = []

            def run_retention_once():
                """Rotate this source's versions, at most once per source."""
                if retention_ran:
                    return ''
                retention_ran.append(True)
                return self._cleanup_old_backup_versions(source_id)

            try:
                validate_source_id(source_id)

                # Get handler for source type
                handler_class = self.handlers.get(source_type)
                if not handler_class:
                    raise ValueError(f"Unsupported source type: {source_type}")

                # Create destination path
                source_dir = source_backup_path(self.backup_base_path, source_id)
                os.makedirs(source_dir, exist_ok=True)

                # The handler writes into a per-run staging (or sync) directory;
                # the run becomes exactly one timestamped artifact afterwards.
                handler = handler_class(source, source_dir)
                artifact = RunArtifact(
                    source_dir,
                    source_id,
                    datetime.now().strftime(TIMESTAMP_FORMAT),
                    handler.artifact_mode(),
                )
                handler.dest_path = artifact.prepare()
                logger.info(f"Backup destination: {handler.dest_path} ({artifact.mode})")

                # Execute backup with live log flushing to DB

                def _flush_logs(logs_text, _result=result):
                    try:
                        _result.logs = logs_text
                        db.session.commit()
                    except Exception:
                        pass

                handler._live_log_callback = _flush_logs
                try:
                    backup_result = normalize_backup_result(handler.backup())
                except BaseException:
                    artifact.discard()
                    raise
                artifact_log = artifact.finalize(backup_result['status'])
                # Retention also has to run when the handler failed - see the
                # finally block. A source that keeps failing would otherwise
                # never rotate and grow without limit.
                cleanup_logs = run_retention_once()

                # Update result
                result.status = backup_result['status']
                result.completed_at = utc_now_naive()
                result.duration = int((result.completed_at - result.started_at).total_seconds())
                result.files_synced = backup_result.get('files_synced', 0)
                result.size_synced = backup_result.get('size_synced', 0)
                result.progress = 100
                result.error_message = '; '.join(backup_result['errors'][:5]) or None
                result.logs = '\n'.join(
                    part for part in [backup_result.get('logs', ''), artifact_log, cleanup_logs]
                    if part
                )

                db.session.commit()

                logger.info(
                    f"Source {source_id} finished with status {result.status}: "
                    f"{result.files_synced} files, {result.size_synced} bytes, {result.duration}s"
                )

                return {
                    'status': result.status,
                    'size_synced': result.size_synced
                }

            except Exception as e:
                import traceback
                logger.error(f"Error backing up source {source_id}: {e}")
                logger.error(f"Traceback: {traceback.format_exc()}")
                result.status = 'failed'
                result.error_message = str(e)
                result.completed_at = utc_now_naive()
                result.duration = int((result.completed_at - result.started_at).total_seconds())
                db.session.commit()

                # A source whose handler keeps failing (expired credentials,
                # host down) must still rotate its existing versions, or it
                # grows until the disk is full while the visible error talks
                # about something else entirely.
                try:
                    cleanup_logs = run_retention_once()
                    if cleanup_logs:
                        result.logs = '\n'.join(
                            part for part in [result.logs or '', cleanup_logs] if part
                        )
                        db.session.commit()
                except Exception as cleanup_error:
                    logger.error(f"Retention after failure of {source_id}: {cleanup_error}")

                return {
                    'status': 'failed',
                    'size_synced': 0
                }

    def _cleanup_old_backup_versions(self, source_id):
        """Keep only the newest timestamped backup versions for one source."""
        if not self._auto_cleanup_enabled():
            return ''

        keep_count = self._backup_retention_count()
        try:
            source_dir = source_backup_path(self.backup_base_path, source_id)
        except ValueError:
            logger.warning(f"Cleanup skipped for invalid source id: {source_id!r}")
            return 'Cleanup übersprungen: ungültige Source-ID'
        if keep_count < 1 or not os.path.isdir(source_dir):
            return ''

        real_base = os.path.realpath(self.backup_base_path)
        real_source_dir = os.path.realpath(source_dir)
        if not real_source_dir.startswith(real_base + os.sep):
            logger.warning(f"Cleanup skipped for unsafe source path: {source_dir}")
            return 'Cleanup übersprungen: unsicherer Quellpfad'

        expired = select_expired(os.listdir(source_dir), keep_count)
        if not expired:
            return ''

        deleted = 0
        errors = []

        for name in expired:
            path = os.path.join(source_dir, name)
            real_path = os.path.realpath(path)
            if not real_path.startswith(real_source_dir + os.sep):
                errors.append(f"unsicherer Pfad übersprungen: {path}")
                continue
            try:
                if os.path.isdir(path):
                    shutil.rmtree(path)
                else:
                    os.unlink(path)
                deleted += 1
            except OSError as e:
                errors.append(f"{os.path.basename(path)}: {e}")

        message = (
            f"Cleanup: {deleted} alte Backup-Artefakte entfernt "
            f"(behalte {keep_count} Versionen pro Quelle)."
        )
        if errors:
            message += f" WARNINGS: {'; '.join(errors[:5])}"
        logger.info(f"{source_id}: {message}")
        return message

    def _auto_cleanup_enabled(self):
        value = Setting.get('auto_cleanup')
        if value is None:
            value = os.environ.get('AUTO_CLEANUP', 'true')
        return str(value).lower() in ('true', '1', 'yes', 'on')

    def _backup_retention_count(self):
        value = Setting.get('backup_retention_count')
        if value is None:
            value = os.environ.get('BACKUP_RETENTION_COUNT', DEFAULT_BACKUP_RETENTION_COUNT)
        try:
            return max(1, int(value))
        except (TypeError, ValueError):
            return DEFAULT_BACKUP_RETENTION_COUNT
