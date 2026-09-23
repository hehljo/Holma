"""
Rsync over SSH Backup Handler
For NAS systems, remote servers, and SSH-enabled devices
"""
import subprocess
import logging
import os
import re
import shlex
from app.backup.base import BackupHandler

logger = logging.getLogger(__name__)


class RsyncSSHBackup(BackupHandler):
    """Rsync over SSH backup handler"""

    def backup(self):
        """Execute rsync over SSH backup"""
        host = self.source_config.get('host', '')
        port = int(self.source_config.get('port', 22))
        remote_path = self.source_config.get('path', '/')
        credentials = self.source_config.get('credentials', {})

        if not host:
            raise Exception("Host is required for rsync over SSH")

        # Validate port
        if not (1 <= port <= 65535):
            raise Exception("Invalid port number")

        # Get username
        username = self.source_config.get('username') or self._get_env_credential(credentials.get('username_env', 'SSH_USER'))
        if not isinstance(username, str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,64}', username):
            raise Exception("Invalid SSH username")
        if not isinstance(host, str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,253}', host):
            raise Exception("Invalid SSH host")
        if not isinstance(remote_path, str) or any(c in remote_path for c in ('\0', '\n', '\r')):
            raise Exception("Invalid remote path")

        # Check for SSH key
        ssh_key = self.source_config.get('ssh_key_path') or credentials.get('ssh_key_path', '')
        if ssh_key:
            ssh_key = os.path.expanduser(ssh_key)

        try:
            self.log(f"Starting rsync backup from {host}:{remote_path}")

            # Build rsync command as array (no shell interpretation)
            cmd = ['rsync', '-avz', '--stats', '--protect-args']
            process_env = os.environ.copy()

            options = self.source_config.get('options', {})

            if options.get('delete', False):
                cmd.append('--delete')

            if options.get('compress', True):
                cmd.append('--compress')

            if options.get('recursive', True):
                cmd.append('--recursive')

            # Exclude patterns - validated as simple strings
            excludes = options.get('exclude', [])
            for pattern in excludes:
                if isinstance(pattern, str) and len(pattern) < 256:
                    cmd.extend(['--exclude', pattern])

            # Include patterns
            includes = options.get('include', [])
            for pattern in includes:
                if isinstance(pattern, str) and len(pattern) < 256:
                    cmd.extend(['--include', pattern])

            # SSH options as array elements
            ssh_cmd_parts = ['ssh', '-p', str(port)]

            if ssh_key and os.path.exists(ssh_key):
                ssh_cmd_parts.extend(['-i', ssh_key])
                self.log("Using SSH key authentication")

            # Strict host key checking
            if not options.get('strict_host_key_checking', True):
                ssh_cmd_parts.extend(['-o', 'StrictHostKeyChecking=no'])
                ssh_cmd_parts.extend(['-o', 'UserKnownHostsFile=/dev/null'])

            # Pass SSH command to rsync
            cmd.extend(['-e', shlex.join(ssh_cmd_parts)])

            # Handle password auth via SSHPASS env var (not command line)
            password = self.source_config.get('password', '')
            password_env = credentials.get('password_env', '')
            if (password or password_env) and not ssh_key:
                if not password:
                    password = self._get_env_credential(password_env, required=False)
                if password:
                    cmd = ['sshpass', '-e'] + cmd
                    process_env['SSHPASS'] = password

            # Source and destination
            source = f"{username}@{host}:{remote_path}"
            if not remote_path.endswith('/'):
                source += '/'

            cmd.extend([source, self.dest_path])

            self.log("Executing rsync backup...")

            # Execute rsync
            timeout = int(options.get('timeout', 3600))
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=process_env,
            )

            if result.stdout:
                self.log(result.stdout)

            if result.returncode != 0:
                raise Exception(f"rsync failed with code {result.returncode}")

            # Parse rsync stats
            files_synced = 0
            size_synced = 0

            for line in result.stdout.split('\n'):
                if 'Number of files' in line:
                    try:
                        parts = line.split(':')[1].strip().split()
                        files_synced = int(parts[0].replace(',', ''))
                    except (ValueError, IndexError):
                        pass
                elif 'Total file size' in line:
                    try:
                        size_str = line.split(':')[1].strip().split()[0].replace(',', '')
                        size_synced = int(size_str)
                    except (ValueError, IndexError):
                        pass
                elif 'Total transferred file size' in line:
                    try:
                        size_str = line.split(':')[1].strip().split()[0].replace(',', '')
                        if size_synced == 0:
                            size_synced = int(size_str)
                    except (ValueError, IndexError):
                        pass

            self.log(f"Rsync backup completed: {files_synced} files, {size_synced} bytes")

            return {
                'files_synced': files_synced,
                'size_synced': size_synced,
                'logs': self.get_logs()
            }

        except subprocess.TimeoutExpired:
            self.log("ERROR: Rsync backup timeout")
            raise Exception("Rsync backup timeout")
        except Exception as e:
            self.log(f"ERROR: Rsync backup failed")
            raise


class NASBackup(RsyncSSHBackup):
    """
    Convenience class for NAS backups (Synology, QNAP, TrueNAS, etc.)
    Uses rsync over SSH
    """
    pass
