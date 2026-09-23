"""
Self-Hosted Services Backup Handler
Backs up various self-hosted services like Plex, Jellyfin, Home Assistant, etc.
"""
import subprocess
import logging
import os
import json
import requests
from datetime import datetime
from app.backup.base import BackupHandler
from app.config import Config
from app.credential_files import mysql_defaults_file

logger = logging.getLogger(__name__)


class SelfHostedBackup(BackupHandler):
    """Generic self-hosted service backup handler"""

    def backup(self):
        """Execute self-hosted service backup"""
        service_type = self.source_config.get('type', 'unknown')
        self.log(f"Starting backup for {service_type} service")

        options = self.source_config.get('options', {})
        backup_method = options.get('backup_method') or self.source_config.get(
            'backup_method', 'docker-volume'
        )

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        total_size = 0
        files_backed_up = 0

        try:
            # Determine backup method
            if backup_method == 'docker-volume':
                result = self._backup_docker_volumes(timestamp)
            elif backup_method in ['api', 'snapshot_api', 'json_export', 'xml_api']:
                result = self._backup_via_api(timestamp)
            elif backup_method == 'rsync':
                result = self._backup_via_rsync(timestamp)
            else:
                raise Exception(f"Unsupported backup method: {backup_method}")

            # Also backup database if specified
            if options.get('backup_database', False):
                db_result = self._backup_database(timestamp)
                result['files_synced'] += db_result.get('files_synced', 0)
                result['size_synced'] += db_result.get('size_synced', 0)

            self.log(f"{service_type} backup completed: {result['files_synced']} items, {result['size_synced']} bytes")

            return result

        except Exception as e:
            self.log(f"ERROR: {str(e)}")
            raise

    def test_connection(self):
        """Run a read-only authentication test for supported service APIs."""
        service_type = self.source_config.get('type')
        if service_type != 'portainer':
            raise Exception(f'Connection test is not implemented for {service_type}')
        credentials = self.source_config.get('credentials', {})
        api_key = self.source_config.get('api_key') or self.source_config.get('token')
        if not api_key and credentials.get('api_key_env'):
            api_key = self._get_env_credential(
                credentials['api_key_env'], required=False
            )
        if not api_key:
            raise Exception('Portainer API key is missing')
        response = self._api_get(
            f'{self._service_base_url()}/api/stacks',
            headers={'X-API-Key': api_key},
        )
        response.raise_for_status()
        stacks = response.json()
        return len(stacks) if isinstance(stacks, list) else 0

    def _backup_docker_volumes(self, timestamp):
        """Backup Docker volumes"""
        self.log("Backing up via Docker volumes")

        service_name = self.source_config.get('id', 'service')
        total_size = 0
        files_backed_up = 0
        errors = []

        # Find volumes for this service
        try:
            # Get all volumes matching service name
            list_cmd = ['docker', 'volume', 'ls', '--format', '{{.Name}}']
            result = subprocess.run(list_cmd, capture_output=True, text=True, check=True)

            volumes = [v for v in result.stdout.strip().split('\n') if service_name in v or self._matches_service(v)]

            if not volumes:
                self.log(f"No Docker volumes found for {service_name}, trying manual volume specification")
                volumes = self._as_list(self.source_config.get('volumes'))
            if not volumes:
                raise Exception(f"No Docker volumes found or configured for {service_name}")

            for volume in volumes:
                if not volume:
                    continue

                self.log(f"Backing up volume: {volume}")

                backup_file = os.path.join(
                    self.dest_path,
                    f"{volume}_{timestamp}.tar.gz"
                )

                # Use docker run with alpine to tar the volume
                cmd = [
                    'docker', 'run', '--rm',
                    '-v', f'{volume}:/volume:ro',
                    '-v', f'{self.dest_path}:/backup',
                    Config.DOCKER_HELPER_IMAGE,
                    'tar', 'czf',
                    f'/backup/{volume}_{timestamp}.tar.gz',
                    '-C', '/volume', '.'
                ]

                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=3600
                )

                if result.returncode != 0:
                    message = f"Volume backup failed for {volume}: {result.stderr[:500]}"
                    errors.append(message)
                    self.log(f"ERROR: {message}")
                    continue

                size = self._get_file_size(backup_file)
                total_size += size
                files_backed_up += 1

                self.log(f"Volume {volume} backed up: {size} bytes")

        except subprocess.CalledProcessError as e:
            self.log(f"ERROR: Could not list Docker volumes: {e}")
            raise
        except Exception as e:
            self.log(f"ERROR: Docker volume backup encountered error: {e}")
            raise

        return {
            'files_synced': files_backed_up,
            'size_synced': total_size,
            'logs': self.get_logs(),
            'errors': errors,
        }

    def _backup_via_api(self, timestamp):
        """Backup via service API"""
        self.log("Backing up via API")

        host = self.source_config.get('host', 'localhost')
        port = self.source_config.get('port', 80)
        service_type = self.source_config.get('type', 'unknown')

        backup_file = os.path.join(
            self.dest_path,
            f"{service_type}_api_backup_{timestamp}.json"
        )

        try:
            # Get credentials
            credentials = self.source_config.get('credentials', {})
            headers = {}

            token = self.source_config.get('token') or self.source_config.get('api_key')
            if token:
                headers['Authorization'] = f'Bearer {token}'
            elif 'token_env' in credentials:
                token = self._get_env_credential(credentials['token_env'], required=False)
                if token:
                    headers['Authorization'] = f'Bearer {token}'
            elif 'api_key_env' in credentials:
                api_key = self._get_env_credential(credentials['api_key_env'], required=False)
                if api_key:
                    headers['X-API-Key'] = api_key

            # Service-specific API endpoints
            if service_type in ('portainer', 'syncthing') and token:
                headers = {'X-API-Key': token}

            data = self._fetch_service_data(host, port, service_type, headers)

            if not data:
                raise Exception(f"API returned no backup data for {service_type}")

            errors = data.pop('_errors', [])
            with open(backup_file, 'w') as f:
                json.dump(data, f, indent=2)

            size = self._get_file_size(backup_file)
            self.log(f"API data backed up: {size} bytes")

            return {
                'files_synced': 1,
                'size_synced': size,
                'logs': self.get_logs(),
                'errors': errors,
            }

        except Exception as e:
            self.log(f"ERROR: API backup failed: {e}")
            raise

    def _backup_via_rsync(self, timestamp):
        """Backup via rsync"""
        self.log("Backing up via rsync")

        options = self.source_config.get('options', {})
        source_path = options.get('vault_path') or options.get('backup_path', '/data')

        try:
            cmd = [
                'rsync', '-avz', '--progress',
                source_path,
                self.dest_path
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=3600
            )

            if result.returncode == 0:
                size = self._get_directory_size(self.dest_path)
                self.log(f"Rsync completed: {size} bytes")

                return {
                    'files_synced': 1,
                    'size_synced': size,
                    'logs': self.get_logs()
                }
            raise Exception(f"rsync failed with code {result.returncode}: {result.stderr[:500]}")
        except Exception as e:
            self.log(f"ERROR: Rsync backup failed: {e}")
            raise

    def _backup_database(self, timestamp):
        """Backup service database"""
        self.log("Backing up database")

        options = self.source_config.get('options', {})
        db_type = options.get('db_type', 'sqlite')
        service_id = self.source_config.get('id', 'service')

        backup_file = os.path.join(
            self.dest_path,
            f"{service_id}_db_{timestamp}.sql"
        )

        try:
            if db_type == 'sqlite':
                # Try to find SQLite database in Docker volume
                return self._backup_docker_volumes(timestamp)
            elif db_type in ['mysql', 'mariadb']:
                return self._backup_mysql_db(backup_file, timestamp)
            elif db_type in ['postgresql', 'postgres']:
                return self._backup_postgres_db(backup_file, timestamp)
            raise Exception(f"Unsupported database type: {db_type}")
        except Exception as e:
            self.log(f"ERROR: Database backup failed: {e}")
            raise

    def _backup_mysql_db(self, backup_file, timestamp):
        """Backup MySQL/MariaDB database"""
        host = self.source_config.get('host', 'localhost')
        credentials = self.source_config.get('credentials', {})

        username = self._get_env_credential(credentials.get('username_env', 'MYSQL_USER'), required=False)
        password = self._get_env_credential(credentials.get('password_env', 'MYSQL_PASSWORD'), required=False)

        if username and password:
            port = int(self.source_config.get('port', 3306))
            with mysql_defaults_file(host, port, username, password) as defaults_file:
                cmd = [
                    'mysqldump',
                    f'--defaults-extra-file={defaults_file}',
                    '--all-databases',
                ]

                with open(backup_file, 'w') as f:
                    result = subprocess.run(
                        cmd, stdout=f, stderr=subprocess.PIPE, text=True
                    )

            if result.returncode == 0:
                size = self._get_file_size(backup_file)
                self.log(f"MySQL database backed up: {size} bytes")
                return {'files_synced': 1, 'size_synced': size}

        raise Exception("MySQL credentials missing or mysqldump failed")

    def _backup_postgres_db(self, backup_file, timestamp):
        """Backup PostgreSQL database"""
        host = self.source_config.get('host', 'localhost')
        credentials = self.source_config.get('credentials', {})

        username = self._get_env_credential(credentials.get('username_env', 'POSTGRES_USER'), required=False)
        password = self._get_env_credential(credentials.get('password_env', 'POSTGRES_PASSWORD'), required=False)

        if username:
            env = os.environ.copy()
            if password:
                env['PGPASSWORD'] = password

            cmd = [
                'pg_dumpall',
                '-h', host,
                '-U', username
            ]

            with open(backup_file, 'w') as f:
                result = subprocess.run(cmd, stdout=f, stderr=subprocess.PIPE, text=True, env=env)

            if result.returncode == 0:
                size = self._get_file_size(backup_file)
                self.log(f"PostgreSQL database backed up: {size} bytes")
                return {'files_synced': 1, 'size_synced': size}

        raise Exception("PostgreSQL credentials missing or pg_dumpall failed")

    def _fetch_service_data(self, host, port, service_type, headers):
        """Fetch data from service-specific API endpoints"""
        base_url = self._service_base_url(host, port)

        try:
            # Service-specific API endpoints
            if service_type == 'homeassistant':
                return self._fetch_homeassistant_data(base_url, headers)
            elif service_type == 'grafana':
                return self._fetch_grafana_data(base_url, headers)
            elif service_type == 'portainer':
                return self._fetch_portainer_data(base_url, headers)
            elif service_type == 'syncthing':
                return self._fetch_syncthing_data(base_url, headers)
            elif service_type == 'nodered':
                return self._fetch_nodered_data(base_url, headers)
            else:
                raise Exception(f"No API backup implementation for {service_type}")
        except Exception as e:
            self.log(f"ERROR: Failed to fetch data from {service_type} API: {e}")
            raise

    def _fetch_homeassistant_data(self, base_url, headers):
        """Fetch Home Assistant data"""
        data = {}
        try:
            # Get config
            response = self._api_get(f"{base_url}/api/config", headers=headers)
            response.raise_for_status()
            data['config'] = response.json()

            # Get states
            response = self._api_get(f"{base_url}/api/states", headers=headers)
            response.raise_for_status()
            data['states'] = response.json()

            self.log("Home Assistant data fetched successfully")
        except Exception as e:
            self.log(f"ERROR: Failed to fetch Home Assistant data: {e}")
            raise

        return data

    def _service_base_url(self, host=None, port=None):
        host = host or self.source_config.get('host', 'localhost')
        port = int(port or self.source_config.get('port', 80))
        if not (1 <= port <= 65535):
            raise Exception('Invalid service API port')
        use_https = self.source_config.get('https')
        if use_https is None:
            use_https = port in (443, 9443)
        scheme = 'https' if use_https else 'http'
        return f'{scheme}://{host}:{port}'

    def _fetch_grafana_data(self, base_url, headers):
        """Fetch Grafana dashboards"""
        data = {}
        try:
            # Get all dashboards
            response = self._api_get(f"{base_url}/api/search", headers=headers)
            response.raise_for_status()
            dashboards = response.json()
            data['dashboards'] = []

            for dashboard in dashboards:
                if dashboard['type'] == 'dash-db':
                    uid = dashboard['uid']
                    dash_response = self._api_get(
                        f"{base_url}/api/dashboards/uid/{uid}",
                        headers=headers,
                    )
                    dash_response.raise_for_status()
                    data['dashboards'].append(dash_response.json())

            self.log(f"Grafana: {len(data['dashboards'])} dashboards fetched")
        except Exception as e:
            self.log(f"ERROR: Failed to fetch Grafana data: {e}")
            raise

        return data

    def _fetch_portainer_data(self, base_url, headers):
        """Export Portainer stack metadata and retrievable stack files."""
        data = {'stack_files': {}}
        errors = []
        try:
            response = self._api_get(f"{base_url}/api/stacks", headers=headers)
            response.raise_for_status()
            data['stacks'] = response.json()
            for stack in data['stacks']:
                stack_id = stack.get('Id')
                if not isinstance(stack_id, int):
                    continue
                try:
                    file_response = self._api_get(
                        f"{base_url}/api/stacks/{stack_id}/file",
                        headers=headers,
                    )
                    file_response.raise_for_status()
                    data['stack_files'][str(stack_id)] = file_response.json()
                except requests.RequestException:
                    errors.append(f'Could not export Portainer stack file {stack_id}')
            if errors:
                data['_errors'] = errors
            self.log(
                f"Portainer: {len(data['stacks'])} stacks and "
                f"{len(data['stack_files'])} stack files fetched"
            )
        except Exception as e:
            self.log(f"ERROR: Failed to fetch Portainer data: {e}")
            raise

        return data

    def _fetch_syncthing_data(self, base_url, headers):
        """Fetch Syncthing configuration"""
        data = {}
        try:
            # Get config
            response = self._api_get(
                f"{base_url}/rest/system/config", headers=headers
            )
            response.raise_for_status()
            data['config'] = response.json()
            self.log("Syncthing config fetched successfully")
        except Exception as e:
            self.log(f"ERROR: Failed to fetch Syncthing data: {e}")
            raise

        return data

    def _fetch_nodered_data(self, base_url, headers):
        """Fetch Node-RED flows"""
        data = {}
        try:
            # Get flows
            auth = None
            credentials = self.source_config.get('credentials', {})
            if 'username_env' in credentials and 'password_env' in credentials:
                username = self._get_env_credential(credentials['username_env'], required=False)
                password = self._get_env_credential(credentials['password_env'], required=False)
                if username and password:
                    auth = (username, password)

            response = self._api_get(
                f"{base_url}/flows", headers=headers, auth=auth
            )
            response.raise_for_status()
            data['flows'] = response.json()
            self.log("Node-RED flows fetched successfully")
        except Exception as e:
            self.log(f"ERROR: Failed to fetch Node-RED data: {e}")
            raise

        return data

    def _api_get(self, url, headers=None, auth=None):
        """Run a read-only API request with explicit TLS verification policy."""
        options = self.source_config.get('options', {})
        return requests.get(
            url,
            headers=headers,
            auth=auth,
            timeout=(10, 30),
            verify=options.get('verify_ssl', True),
        )

    def _matches_service(self, volume_name):
        """Check if volume name matches the service"""
        service_type = self.source_config.get('type', '').lower()
        service_id = self.source_config.get('id', '').lower()
        volume_lower = volume_name.lower()

        return service_type in volume_lower or service_id in volume_lower
