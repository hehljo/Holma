"""
Local Backup Handler
Best Practice 02/2026: Uses rsync with --stats, extends BackupHandler
"""
import subprocess
import logging
import os
from app.backup.base import BackupHandler

logger = logging.getLogger(__name__)


class LocalBackup(BackupHandler):
    """Handles local directory backups using rsync"""

    ARTIFACT_MODE = 'snapshot'

    def backup(self):
        """Execute local backup"""
        sources = self._as_list(self.source_config.get('sources'))
        if not sources and self.source_config.get('path'):
            sources = [self.source_config.get('path')]

        if not sources:
            raise Exception("No source paths specified for local backup")

        total_files = 0
        total_size = 0
        errors = []

        for source_path in sources:
            try:
                self.log(f"Backing up: {source_path}")

                # Verify source exists
                if not os.path.exists(source_path):
                    message = f"Source path does not exist: {source_path}"
                    errors.append(message)
                    self.log(f"ERROR: {message}")
                    continue

                # Create destination subdirectory
                source_name = os.path.basename(source_path.rstrip('/'))
                dest_subpath = os.path.join(self.dest_path, source_name)

                # Build rsync command
                result = self._rsync_path(source_path, dest_subpath)

                total_files += result['files_synced']
                total_size += result['size_synced']

            except Exception as e:
                message = f"Failed to back up {source_path}: {str(e)}"
                errors.append(message)
                self.log(f"ERROR: {message}")
                logger.error(f"Error backing up {source_path}: {e}")

        return {
            'files_synced': total_files,
            'size_synced': total_size,
            'logs': self.get_logs(),
            'errors': errors,
        }

    def _rsync_path(self, source, dest):
        """Rsync a single path"""
        options = self.source_config.get('options', {})

        # Build rsync command
        cmd = ['rsync', '-av', '--stats']

        if options.get('recursive', True):
            cmd.append('-r')

        if options.get('delete', False):
            cmd.append('--delete')

        if not options.get('follow_symlinks', False):
            cmd.append('--no-links')

        # Exclude patterns
        for pattern in options.get('exclude', []):
            cmd.extend(['--exclude', pattern])

        # Ensure source ends with / for directory contents
        if os.path.isdir(source) and not source.endswith('/'):
            source += '/'

        cmd.extend([source, dest])

        self.log(f"Running: {' '.join(cmd)}")

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
            raise Exception(f"rsync failed with code {result.returncode}")

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
