"""
WebDAV Backup Handler
Supports: Nextcloud, Seafile, ownCloud, and generic WebDAV servers
"""
import subprocess
import logging
import os
from app.backup.base import BackupHandler

logger = logging.getLogger(__name__)


class WebDAVBackup(BackupHandler):
    """WebDAV backup handler using rclone or davfs2"""

    ARTIFACT_MODE = 'snapshot'

    def backup(self):
        """Execute WebDAV backup"""
        host = self.source_config.get('host', '')
        path = self.source_config.get('path', '/')
        credentials = self.source_config.get('credentials', {})

        if not host:
            raise Exception("WebDAV host is required")

        # Get credentials
        username = self.source_config.get('username') or self._get_env_credential(credentials.get('username_env', 'WEBDAV_USER'))
        password = self.source_config.get('password') or self._get_env_credential(credentials.get('password_env', 'WEBDAV_PASSWORD'))

        # Determine protocol
        use_https = self.source_config.get('https', True)
        protocol = 'https' if use_https else 'http'
        url = f"{protocol}://{host}{path}"

        try:
            self.log(f"Starting WebDAV backup from {url}")

            # Use rclone for WebDAV sync
            method = self.source_config.get('method', 'rclone')

            if method == 'rclone':
                return self._backup_with_rclone(url, username, password)
            else:
                return self._backup_with_davfs(url, username, password)

        except Exception as e:
            self.log(f"ERROR: {str(e)}")
            raise

    def _backup_with_rclone(self, url, username, password):
        """Backup using rclone WebDAV backend"""
        self.log("Using rclone for WebDAV backup")

        # Create temporary rclone config
        remote_name = 'webdav_temp'

        # Set rclone environment variables
        env = os.environ.copy()
        env['RCLONE_CONFIG_WEBDAV_TEMP_TYPE'] = 'webdav'
        env['RCLONE_CONFIG_WEBDAV_TEMP_URL'] = url
        env['RCLONE_CONFIG_WEBDAV_TEMP_VENDOR'] = self.source_config.get('vendor', 'other')
        env['RCLONE_CONFIG_WEBDAV_TEMP_USER'] = username
        env['RCLONE_CONFIG_WEBDAV_TEMP_PASS'] = password

        options = self.source_config.get('options', {})

        # Build rclone command
        cmd = [
            'rclone', 'sync',
            f'{remote_name}:/',
            self.dest_path,
            '--verbose',
            '--stats', '1s',
            f'--transfers={options.get("transfers", 4)}',
            f'--checkers={options.get("checkers", 8)}'
        ]

        if options.get('delete', False):
            cmd.append('--delete-excluded')

        # Execute rclone
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            env=env,
            timeout=3600
        )

        if result.stdout:
            self.log(result.stdout)

        if result.returncode != 0:
            raise Exception(f"rclone failed: {result.stderr}")

        # Calculate backup size
        size = self._get_directory_size(self.dest_path)
        files = sum(1 for _, _, files in os.walk(self.dest_path) for _ in files)

        self.log(f"WebDAV backup completed: {files} files, {size} bytes")

        return {
            'files_synced': files,
            'size_synced': size,
            'logs': self.get_logs()
        }

    def _backup_with_davfs(self, url, username, password):
        """Backup using davfs2 mount and rsync"""
        self.log("Using davfs2 for WebDAV backup")

        import tempfile

        # Create temporary mount point
        mount_point = tempfile.mkdtemp(prefix='webdav_mount_')

        try:
            # Create davfs2 secrets file
            secrets_file = tempfile.NamedTemporaryFile(mode='w', delete=False)
            secrets_file.write(f"{url} {username} {password}\n")
            secrets_file.close()

            # Mount WebDAV
            self.log(f"Mounting WebDAV at {mount_point}")

            mount_cmd = [
                'mount.davfs',
                '-o', f'conf=/dev/null,secrets={secrets_file.name}',
                url,
                mount_point
            ]

            subprocess.run(mount_cmd, check=True, timeout=30)

            # Sync using rsync
            self.log("Syncing files with rsync")

            rsync_cmd = [
                'rsync', '-av', '--stats',
                f'{mount_point}/',
                self.dest_path
            ]

            options = self.source_config.get('options', {})
            if options.get('delete', False):
                rsync_cmd.append('--delete')

            result = subprocess.run(
                rsync_cmd,
                capture_output=True,
                text=True,
                timeout=3600
            )

            if result.returncode != 0:
                raise Exception(
                    f"WebDAV rsync failed with code {result.returncode}: {result.stderr[:500]}"
                )

            # Parse rsync stats
            files_synced = 0
            size_synced = 0

            for line in result.stdout.split('\n'):
                if 'Number of files' in line:
                    try:
                        files_synced = int(line.split(':')[1].strip().split()[0].replace(',', ''))
                    except:
                        pass
                if 'Total file size' in line:
                    try:
                        size_str = line.split(':')[1].strip().split()[0].replace(',', '')
                        size_synced = int(size_str)
                    except:
                        pass

            self.log(f"WebDAV backup completed: {files_synced} files, {size_synced} bytes")

            return {
                'files_synced': files_synced,
                'size_synced': size_synced,
                'logs': self.get_logs()
            }

        finally:
            # Cleanup: unmount and remove temp files
            try:
                subprocess.run(['umount', mount_point], timeout=30)
                os.rmdir(mount_point)
                os.unlink(secrets_file.name)
            except:
                pass
