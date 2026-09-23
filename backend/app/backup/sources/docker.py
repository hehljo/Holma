"""
Docker Volume Backup Handler
Backs up Docker volumes and container data
"""
import subprocess
import logging
import os
import hashlib
import re
from datetime import datetime
from app.backup.base import BackupHandler
from app.config import Config

logger = logging.getLogger(__name__)

DOCKER_OBJECT_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.-]{0,254}$')
DOCKER_IMAGE_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_./:@-]{0,511}$')


class DockerVolumeBackup(BackupHandler):
    """Docker volume backup handler"""

    def backup(self):
        """Execute Docker volume backup"""
        volumes = self._as_list(self.source_config.get('volumes'))
        containers = self._as_list(self.source_config.get('containers'))

        if not volumes and not containers:
            raise Exception("No Docker volumes or containers specified")
        if any(not isinstance(volume, str) or not DOCKER_OBJECT_RE.fullmatch(volume)
               for volume in volumes):
            raise Exception('Invalid Docker volume name')
        if any(not isinstance(container, str) or not DOCKER_OBJECT_RE.fullmatch(container)
               for container in containers):
            raise Exception('Invalid Docker container name')

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        total_size = 0
        files_backed_up = 0

        try:
            # Backup volumes
            if volumes:
                for volume in volumes:
                    self.log(f"Backing up Docker volume: {volume}")

                    backup_file = os.path.join(
                        self.dest_path,
                        f"volume_{volume}_{timestamp}.tar.gz"
                    )

                    # Optionally stop container for consistent backup
                    options = self.source_config.get('options', {})
                    stop_containers = options.get('stop_for_backup', False)

                    stopped_containers = []
                    try:
                        if stop_containers:
                            self.log(f"Stopping containers using volume {volume}...")
                            # Find containers using this volume
                            find_cmd = ['docker', 'ps', '-q', '--filter', f'volume={volume}']
                            find_result = subprocess.run(
                                find_cmd, capture_output=True, text=True, timeout=30
                            )
                            if find_result.returncode != 0:
                                raise Exception(
                                    f"Could not list containers for volume {volume}: "
                                    f"{find_result.stderr[:500]}"
                                )
                            container_ids = (
                                find_result.stdout.strip().splitlines()
                                if find_result.stdout.strip() else []
                            )
                            for cid in container_ids:
                                stop_result = subprocess.run(
                                    ['docker', 'stop', cid],
                                    capture_output=True,
                                    text=True,
                                    timeout=60,
                                )
                                if stop_result.returncode != 0:
                                    raise Exception(
                                        f"Could not stop container {cid}: {stop_result.stderr[:500]}"
                                    )
                                stopped_containers.append(cid)

                        # Use docker run with alpine to tar the volume
                        cmd = [
                            'docker', 'run', '--rm',
                            '-v', f'{volume}:/volume:ro',
                            '-v', f'{self.dest_path}:/backup',
                            Config.DOCKER_HELPER_IMAGE,
                            'tar', 'czf',
                            f'/backup/volume_{volume}_{timestamp}.tar.gz',
                            '-C', '/volume', '.'
                        ]

                        result = subprocess.run(
                            cmd,
                            capture_output=True,
                            text=True,
                            timeout=3600
                        )

                        if result.returncode != 0:
                            raise Exception(f"Docker volume backup failed: {result.stderr}")

                        size = self._get_file_size(backup_file)
                        total_size += size
                        files_backed_up += 1

                        self.log(f"Volume {volume} backed up: {size} bytes")
                    finally:
                        restart_failures = []
                        for cid in stopped_containers:
                            start_result = subprocess.run(
                                ['docker', 'start', cid],
                                capture_output=True,
                                text=True,
                                timeout=60,
                            )
                            if start_result.returncode != 0:
                                restart_failures.append(cid)
                                self.log(
                                    f"ERROR: Could not restart container {cid}: "
                                    f"{start_result.stderr[:500]}"
                                )
                        if stopped_containers and not restart_failures:
                            self.log(f"Restarted {len(stopped_containers)} container(s)")

            # Backup container data
            if containers:
                for container in containers:
                    self.log(f"Backing up Docker container: {container}")

                    # Check if container exists
                    check_cmd = ['docker', 'ps', '-a', '--filter', f'name={container}', '--format', '{{.Names}}']
                    check_result = subprocess.run(check_cmd, capture_output=True, text=True)

                    if check_result.returncode != 0:
                        raise Exception(
                            f"Could not inspect Docker containers: {check_result.stderr[:500]}"
                        )

                    existing_names = set(check_result.stdout.strip().splitlines())
                    if container not in existing_names:
                        self.log(f"ERROR: Container {container} not found")
                        continue

                    backup_file = os.path.join(
                        self.dest_path,
                        f"container_{container}_{timestamp}.tar"
                    )

                    # Export container filesystem
                    options = self.source_config.get('options', {})

                    if options.get('export_filesystem', True):
                        export_cmd = ['docker', 'export', container, '-o', backup_file]

                        result = subprocess.run(
                            export_cmd,
                            capture_output=True,
                            text=True,
                            timeout=3600
                        )

                        if result.returncode != 0:
                            raise Exception(f"Container export failed: {result.stderr}")

                        size = self._get_file_size(backup_file)
                        total_size += size
                        files_backed_up += 1

                        self.log(f"Container {container} exported: {size} bytes")

                    # Backup container config
                    if options.get('backup_config', True):
                        config_file = os.path.join(
                            self.dest_path,
                            f"container_{container}_config_{timestamp}.json"
                        )

                        inspect_cmd = ['docker', 'inspect', container]
                        with open(config_file, 'w') as f:
                            subprocess.run(
                                inspect_cmd,
                                stdout=f,
                                stderr=subprocess.PIPE,
                                check=True,
                                timeout=60,
                            )

                        self.log(f"Container {container} config saved")

            self.log(f"Docker backup completed: {files_backed_up} items, {total_size} bytes")

            return {
                'files_synced': files_backed_up,
                'size_synced': total_size,
                'logs': self.get_logs()
            }

        except subprocess.TimeoutExpired:
            self.log("ERROR: Docker backup timeout")
            raise Exception("Docker backup timeout")
        except Exception as e:
            self.log(f"ERROR: {str(e)}")
            raise


class DockerImageBackup(BackupHandler):
    """Docker image backup handler"""

    def backup(self):
        """Execute Docker image backup"""
        images = self._as_list(self.source_config.get('images'))

        if not images:
            raise Exception("No Docker images specified")
        if any(not isinstance(image, str) or not DOCKER_IMAGE_RE.fullmatch(image)
               or '..' in image.split('/') for image in images):
            raise Exception('Invalid Docker image reference')

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        total_size = 0
        files_backed_up = 0

        try:
            for image in images:
                self.log(f"Backing up Docker image: {image}")

                # Sanitize image name for filename
                slug = re.sub(r'[^A-Za-z0-9_.-]+', '_', image)[:100]
                digest = hashlib.sha256(image.encode('utf-8')).hexdigest()[:12]
                safe_name = f'{slug}_{digest}'
                backup_file = os.path.join(
                    self.dest_path,
                    f"image_{safe_name}_{timestamp}.tar"
                )

                # Save image to tar file
                cmd = ['docker', 'save', '-o', backup_file, image]

                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=3600
                )

                if result.returncode != 0:
                    raise Exception(f"Image save failed: {result.stderr}")

                # Optionally compress
                options = self.source_config.get('options', {})
                if options.get('compress', True):
                    self.log(f"Compressing image backup...")
                    subprocess.run(['gzip', backup_file], check=True)
                    backup_file += '.gz'
                size = self._get_file_size(backup_file)
                total_size += size
                files_backed_up += 1
                self.log(f"Image {image} saved: {size} bytes")

            self.log(f"Docker image backup completed: {files_backed_up} images, {total_size} bytes")

            return {
                'files_synced': files_backed_up,
                'size_synced': total_size,
                'logs': self.get_logs()
            }

        except subprocess.TimeoutExpired:
            self.log("ERROR: Docker image backup timeout")
            raise Exception("Docker image backup timeout")
        except Exception as e:
            self.log(f"ERROR: {str(e)}")
            raise
