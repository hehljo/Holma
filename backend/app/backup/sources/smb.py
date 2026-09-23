"""
SMB/NFS Backup Handler
Best Practice 02/2026: Extends BackupHandler, SMB version auto-detection,
lazy unmount fallback, consistent logging
"""
import subprocess
import logging
import os
import re
import tarfile
import tempfile
from datetime import datetime
from app.backup.base import BackupHandler

logger = logging.getLogger(__name__)


class SMBBackup(BackupHandler):
    """Handles SMB through smbclient and NFS through mount/rsync."""

    def __init__(self, source_config, dest_path):
        super().__init__(source_config, dest_path)
        self.mount_point = None

    def backup(self):
        """Execute SMB/NFS backup"""
        if self.source_config.get('type') != 'nfs':
            return self._backup_smb_archive()

        try:
            # A private, unpredictable directory avoids shared /tmp races.
            self.mount_point = tempfile.mkdtemp(prefix='backupgenie-nfs-')
            self.log(f"Created mount point: {self.mount_point}")

            # NFS still requires a kernel mount in the container.
            self._mount_nfs()

            self.log(f"Mounted {self.source_config.get('source', 'unknown')}")

            # Sync files using rsync
            result = self._rsync_files()

            # Unmount
            self._unmount()
            self.log("Unmounted successfully")

            return {
                'files_synced': result['files_synced'],
                'size_synced': result['size_synced'],
                'logs': self.get_logs()
            }

        except Exception as e:
            self.log(f"ERROR: {str(e)}")
            # Try to unmount even if backup failed
            try:
                self._unmount()
            except Exception:
                pass
            raise

    def _backup_smb_archive(self):
        """Back up SMB through smbclient without privileged kernel mounts."""
        source, username, password, remote_path, options = self._smb_parameters()

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        archive = os.path.join(self.dest_path, f'smb_{timestamp}.tar')
        command, process_env = self._smbclient_command(
            source,
            username,
            password,
            remote_path,
            ['-Tc', '-'],
            encrypt_transport=options.get('encrypt_transport', False),
        )

        self.log(f'Starting SMB backup from {source}')
        try:
            with open(archive, 'wb') as archive_file:
                result = subprocess.run(
                    command,
                    stdout=archive_file,
                    stderr=subprocess.PIPE,
                    env=process_env,
                    timeout=int(options.get('timeout', 3600)),
                )
            if result.returncode != 0:
                message = result.stderr.decode('utf-8', errors='replace')[:500]
                raise Exception(
                    f'smbclient failed with code {result.returncode}: {message}'
                )

            with tarfile.open(archive, 'r:') as tar:
                files = sum(member.isfile() for member in tar.getmembers())
            size = os.path.getsize(archive)
            self.log(f'SMB backup completed: {files} files, {size} bytes')
            return {
                'files_synced': files,
                'size_synced': size,
                'logs': self.get_logs(),
            }
        except Exception:
            if os.path.exists(archive):
                os.unlink(archive)
            self.log('ERROR: SMB backup failed')
            raise

    def test_connection(self):
        """Verify SMB authentication and read access without writing remotely."""
        source, username, password, remote_path, options = self._smb_parameters()
        command, process_env = self._smbclient_command(
            source,
            username,
            password,
            remote_path,
            ['-c', 'ls'],
            encrypt_transport=options.get('encrypt_transport', False),
        )
        result = subprocess.run(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            env=process_env,
            timeout=15,
        )
        if result.returncode != 0:
            raise Exception('SMB authentication or share access failed')
        return True

    def _smb_parameters(self):
        """Resolve and validate the SMB connection contract once."""
        credentials = self.source_config.get('credentials', {})
        username = self.source_config.get('username') or credentials.get('username', '')
        password = self._get_config_credential(
            'password', 'NAS_PASSWORD_1', required=False
        )

        source = self.source_config.get('source')
        host = self.source_config.get('host', '')
        share = str(self.source_config.get('share', '')).strip('/')
        if not source and host and share:
            source = f'//{host}/{share}'
        match = re.fullmatch(r'//([A-Za-z0-9_.:-]{1,253})/([^/\\\0\r\n]+)', source or '')
        if not match:
            raise Exception('Invalid SMB source; expected //host/share')
        if username and not re.fullmatch(r'[A-Za-z0-9_.@\\/-]{1,128}', username):
            raise Exception('Invalid SMB username')

        options = self.source_config.get('options', {})
        remote_path = str(self.source_config.get('path', '')).strip('/')
        if any(character in remote_path for character in ('\0', '\r', '\n')):
            raise Exception('Invalid SMB path')

        return source, username, password, remote_path, options

    @staticmethod
    def _smbclient_command(
        source,
        username,
        password,
        remote_path,
        operation,
        *,
        encrypt_transport=False,
    ):
        """Build a non-interactive command without placing secrets in argv."""
        command = ['smbclient', source, '-d', '0', '-E']
        if username:
            command.extend(['-U', username])
        if remote_path:
            command.extend(['-D', remote_path])
        protection = 'encrypt' if encrypt_transport else 'sign'
        command.append(f'--client-protection={protection}')
        if not password:
            command.append('-N')
        command.extend(operation)

        process_env = os.environ.copy()
        if password:
            process_env['PASSWD'] = password

        return command, process_env

    def _mount_nfs(self):
        """Mount NFS share"""
        options = self.source_config.get('options', {})
        vers = options.get('vers', 3)
        nolock = ',nolock' if options.get('nolock', False) else ''
        source = self.source_config.get('source')
        if not source:
            host = self.source_config.get('host', '')
            share = self.source_config.get('share', '')
            if host and share:
                source = f"{host}:{share}"
        if not source:
            raise Exception("NFS source missing. Configure source or host/share.")

        cmd = [
            'mount',
            '-t', 'nfs',
            '-o', f'vers={vers}{nolock}',
            source,
            self.mount_point
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            raise Exception(f"NFS mount failed: {result.stderr}")
        self.log(f"NFS mounted with vers={vers}")

    def _rsync_files(self):
        """Sync files using rsync"""
        options = self.source_config.get('options', {})

        # Build rsync command
        cmd = ['rsync', '-av', '--stats']

        if options.get('recursive', True):
            cmd.append('-r')

        if options.get('delete', False):
            cmd.append('--delete')

        # Exclude patterns
        for pattern in options.get('exclude', []):
            cmd.extend(['--exclude', pattern])

        cmd.extend([
            f"{self.mount_point}/",
            self.dest_path
        ])

        self.log(f"Running rsync...")

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=options.get('timeout', 3600)
        )

        if result.stdout:
            self.log(result.stdout)
        if result.stderr:
            self.log(result.stderr)

        if result.returncode != 0:
            raise Exception(f"rsync failed with code {result.returncode}: {result.stderr[:500]}")

        # Parse rsync stats
        files_synced = 0
        size_synced = 0

        for line in result.stdout.split('\n'):
            if 'Number of files' in line:
                try:
                    files_synced = int(line.split(':')[1].strip().split()[0].replace(',', ''))
                except Exception:
                    pass
            if 'Total file size' in line:
                try:
                    size_str = line.split(':')[1].strip().split()[0].replace(',', '')
                    size_synced = int(size_str)
                except Exception:
                    pass

        return {
            'files_synced': files_synced,
            'size_synced': size_synced,
        }

    def _unmount(self):
        """Unmount the share with lazy fallback"""
        if not self.mount_point:
            return
        result = subprocess.run(['umount', self.mount_point], capture_output=True)
        if result.returncode != 0:
            # Lazy unmount as fallback for busy mount points
            subprocess.run(['umount', '-l', self.mount_point], capture_output=True)
        try:
            os.rmdir(self.mount_point)
        except Exception:
            pass
