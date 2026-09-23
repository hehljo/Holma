"""
FTP/SFTP Backup Handler
Supports: FTP, FTPS, SFTP
"""
import subprocess
import logging
import os
import shlex
import re
from app.backup.base import BackupHandler

logger = logging.getLogger(__name__)


class FTPBackup(BackupHandler):
    """FTP/FTPS backup handler using lftp"""

    ARTIFACT_MODE = 'snapshot'

    def backup(self):
        """Execute FTP backup using lftp mirror"""
        host = self.source_config.get('host', 'localhost')
        port = int(self.source_config.get('port', 21))
        credentials = self.source_config.get('credentials', {})
        remote_path = self.source_config.get('path', '/')

        # Validate inputs
        if not host or not host.replace('.', '').replace('-', '').replace('_', '').isalnum():
            raise Exception("Invalid hostname")
        if not (1 <= port <= 65535):
            raise Exception("Invalid port number")

        # Get credentials
        username = self.source_config.get('username') or self._get_env_credential(credentials.get('username_env', 'FTP_USER'))
        password = self.source_config.get('password') or self._get_env_credential(credentials.get('password_env', 'FTP_PASSWORD'))

        # Check if FTPS is enabled
        use_ftps = self.source_config.get('ftps', False)
        protocol = 'ftps' if use_ftps else 'ftp'

        try:
            self.log(f"Starting FTP backup from {protocol}://{host}:{port}{remote_path}")

            options = self.source_config.get('options', {})
            parallel = int(options.get('parallel', 2))
            if not (1 <= parallel <= 10):
                parallel = 2

            # Build lftp script file to avoid command injection
            # Use lftp's set command for credentials instead of URL embedding
            lftp_commands = [
                f"set net:timeout 30",
                f"set net:max-retries 3",
                f"open -u {shlex.quote(username)},{shlex.quote(password)} "
                f"-p {port} {protocol}://{shlex.quote(host)}",
            ]

            mirror_cmd = f"mirror --verbose --parallel={parallel}"

            if options.get('delete', False):
                mirror_cmd += " --delete"
            if options.get('only_newer', True):
                mirror_cmd += " --only-newer"

            mirror_cmd += f" {shlex.quote(remote_path)} {shlex.quote(self.dest_path)}"
            lftp_commands.append(mirror_cmd)
            lftp_commands.append("bye")

            lftp_script = '\n'.join(lftp_commands)

            # Write script to temp file instead of passing via -c
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', suffix='.lftp', delete=False) as f:
                f.write(lftp_script)
                script_path = f.name

            try:
                result = subprocess.run(
                    ['lftp', '-f', script_path],
                    capture_output=True,
                    text=True,
                    timeout=3600
                )
            finally:
                os.unlink(script_path)

            if result.stdout:
                self.log(result.stdout)

            if result.returncode != 0:
                raise Exception(
                    f"lftp failed with code {result.returncode}: {result.stderr[:500]}"
                )

            # Calculate backup size
            size = self._get_directory_size(self.dest_path)
            files = sum(1 for _, _, files in os.walk(self.dest_path) for _ in files)

            self.log(f"FTP backup completed: {files} files, {size} bytes")

            return {
                'files_synced': files,
                'size_synced': size,
                'logs': self.get_logs()
            }

        except subprocess.TimeoutExpired:
            self.log("ERROR: FTP backup timeout")
            raise Exception("FTP backup timeout")
        except Exception as e:
            self.log(f"ERROR: FTP backup failed")
            raise


class SFTPBackup(BackupHandler):
    """SFTP backup handler using rsync over SSH"""

    ARTIFACT_MODE = 'snapshot'

    def backup(self):
        """Execute SFTP backup using rsync"""
        host = self.source_config.get('host', 'localhost')
        port = int(self.source_config.get('port', 22))
        credentials = self.source_config.get('credentials', {})
        remote_path = self.source_config.get('path', '/')

        # Validate inputs
        if not (1 <= port <= 65535):
            raise Exception("Invalid port number")

        # Get credentials
        username = self.source_config.get('username') or self._get_env_credential(credentials.get('username_env', 'SFTP_USER'))
        if not isinstance(username, str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,64}', username):
            raise Exception("Invalid SFTP username")
        if not isinstance(host, str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,253}', host):
            raise Exception("Invalid SFTP host")
        if not isinstance(remote_path, str) or any(c in remote_path for c in ('\0', '\n', '\r')):
            raise Exception("Invalid SFTP path")

        # Check for SSH key or password
        ssh_key = self.source_config.get('ssh_key_path') or credentials.get('ssh_key_path', '')
        password = self.source_config.get('password', '')
        password_env = credentials.get('password_env', '')

        try:
            self.log(f"Starting SFTP backup from {host}:{remote_path}")

            # Build rsync command as array (no shell interpretation)
            cmd = ['rsync', '-avz', '--stats', '--protect-args']
            process_env = os.environ.copy()

            options = self.source_config.get('options', {})

            if options.get('delete', False):
                cmd.append('--delete')

            if options.get('compress', True):
                cmd.append('--compress')

            # SSH options as array
            ssh_cmd = ['ssh', '-p', str(port)]
            if ssh_key and os.path.exists(ssh_key):
                ssh_cmd.extend(['-i', ssh_key])
                self.log(f"Using SSH key authentication")
            elif password or password_env:
                # Use sshpass with SSHPASS env var (not command line)
                if not password:
                    password = self._get_env_credential(password_env)
                cmd = ['sshpass', '-e'] + cmd
                process_env['SSHPASS'] = password

            cmd.extend(['-e', shlex.join(ssh_cmd)])

            # Add source and destination
            source = f"{username}@{host}:{remote_path}"
            cmd.extend([source, self.dest_path])

            # Execute rsync
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=3600,
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
                        files_synced = int(line.split(':')[1].strip().split()[0].replace(',', ''))
                    except (ValueError, IndexError):
                        pass
                if 'Total file size' in line:
                    try:
                        size_str = line.split(':')[1].strip().split()[0].replace(',', '')
                        size_synced = int(size_str)
                    except (ValueError, IndexError):
                        pass

            self.log(f"SFTP backup completed: {files_synced} files, {size_synced} bytes")

            return {
                'files_synced': files_synced,
                'size_synced': size_synced,
                'logs': self.get_logs()
            }

        except subprocess.TimeoutExpired:
            self.log("ERROR: SFTP backup timeout")
            raise Exception("SFTP backup timeout")
        except Exception as e:
            self.log(f"ERROR: SFTP backup failed")
            raise
