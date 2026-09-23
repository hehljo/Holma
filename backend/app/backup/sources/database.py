"""
Database Backup Handlers
Supports: MySQL, MariaDB, PostgreSQL, MongoDB, Redis, SQLite, CouchDB, InfluxDB
"""
import subprocess
import logging
import os
import shutil
import sqlite3
import requests
from contextlib import closing
from urllib.parse import quote
from pathlib import Path
from datetime import datetime
from app.backup.base import BackupHandler
from app.credential_files import mongodb_password_file, mysql_defaults_file

logger = logging.getLogger(__name__)


class MySQLBackup(BackupHandler):
    """MySQL/MariaDB backup handler using mysqldump"""

    def backup(self):
        """Execute MySQL backup"""
        credentials = self.source_config.get('credentials', {})
        host = self.source_config.get('host', 'localhost')
        port = self.source_config.get('port', 3306)
        databases = self._as_list(self.source_config.get('databases'))
        if not databases and self.source_config.get('database'):
            databases = [self.source_config.get('database')]

        # Get credentials
        username = self.source_config.get('username') or self._get_env_credential(credentials.get('username_env', 'MYSQL_USER'))
        password = self.source_config.get('password') or self._get_env_credential(credentials.get('password_env', 'MYSQL_PASSWORD'))

        if not databases:
            # Backup all databases
            databases = ['--all-databases']
            db_name = 'all_databases'
        else:
            db_name = '_'.join(databases)

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_file = os.path.join(self.dest_path, f"mysql_{db_name}_{timestamp}.sql")

        try:
            self.log(f"Starting MySQL backup: {host}:{port}")

            with mysql_defaults_file(host, port, username, password) as defaults_file:
                cmd = [
                    'mysqldump',
                    f'--defaults-extra-file={defaults_file}',
                    '--single-transaction',
                    '--routines',
                    '--triggers',
                    '--events',
                ]

                options = self.source_config.get('options', {})
                if options.get('compress', True):
                    cmd.append('--compress')

                if databases == ['--all-databases']:
                    cmd.extend(databases)
                else:
                    cmd.append('--databases')
                    cmd.extend(databases)

                with open(backup_file, 'w') as f:
                    result = subprocess.run(
                        cmd,
                        stdout=f,
                        stderr=subprocess.PIPE,
                        text=True,
                        timeout=3600,
                    )

            if result.returncode != 0:
                raise Exception(f"mysqldump failed: {result.stderr}")

            # Optionally compress
            if options.get('gzip', True):
                self.log("Compressing backup with gzip...")
                subprocess.run(['gzip', backup_file], check=True)
                backup_file += '.gz'

            size = self._get_file_size(backup_file)
            self.log(f"MySQL backup completed: {backup_file} ({size} bytes)")

            return {
                'files_synced': len(databases) if databases != ['--all-databases'] else 1,
                'size_synced': size,
                'logs': self.get_logs()
            }

        except subprocess.TimeoutExpired:
            self.log("ERROR: MySQL backup timeout")
            raise Exception("MySQL backup timeout")
        except Exception as e:
            self.log(f"ERROR: {str(e)}")
            raise


class PostgreSQLBackup(BackupHandler):
    """PostgreSQL backup handler using pg_dump"""

    def backup(self):
        """Execute PostgreSQL backup"""
        credentials = self.source_config.get('credentials', {})
        host = self.source_config.get('host', 'localhost')
        port = self.source_config.get('port', 5432)
        databases = self._as_list(self.source_config.get('databases'))
        if not databases and self.source_config.get('database'):
            databases = [self.source_config.get('database')]

        # Get credentials
        username = self.source_config.get('username') or self._get_env_credential(credentials.get('username_env', 'POSTGRES_USER'))
        password = self.source_config.get('password') or self._get_env_credential(credentials.get('password_env', 'POSTGRES_PASSWORD'))

        if not databases:
            databases = ['postgres']  # Default database

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        total_size = 0
        files_backed_up = 0

        # Set password environment variable for pg_dump
        env = os.environ.copy()
        env['PGPASSWORD'] = password

        try:
            for db in databases:
                self.log(f"Starting PostgreSQL backup: {db}@{host}:{port}")

                backup_file = os.path.join(self.dest_path, f"postgres_{db}_{timestamp}.dump")

                # Build pg_dump command
                cmd = [
                    'pg_dump',
                    f'--host={host}',
                    f'--port={port}',
                    f'--username={username}',
                    '--format=custom',
                    '--verbose',
                    db
                ]

                # Add options
                options = self.source_config.get('options', {})
                if options.get('schema_only', False):
                    cmd.append('--schema-only')
                if options.get('data_only', False):
                    cmd.append('--data-only')

                cmd.extend(['--file', backup_file])
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    env=env,
                    timeout=3600
                )

                if result.returncode != 0:
                    raise Exception(f"pg_dump failed: {result.stderr}")

                # Optionally compress
                if options.get('gzip', True):
                    self.log(f"Compressing backup with gzip...")
                    subprocess.run(['gzip', backup_file], check=True)
                    backup_file += '.gz'

                size = self._get_file_size(backup_file)
                total_size += size
                files_backed_up += 1
                self.log(f"PostgreSQL backup completed: {backup_file} ({size} bytes)")

            return {
                'files_synced': files_backed_up,
                'size_synced': total_size,
                'logs': self.get_logs()
            }

        except subprocess.TimeoutExpired:
            self.log("ERROR: PostgreSQL backup timeout")
            raise Exception("PostgreSQL backup timeout")
        except Exception as e:
            self.log(f"ERROR: {str(e)}")
            raise


class MongoDBBackup(BackupHandler):
    """MongoDB backup handler using mongodump"""

    def backup(self):
        """Execute MongoDB backup"""
        credentials = self.source_config.get('credentials', {})
        host = self.source_config.get('host', 'localhost')
        port = self.source_config.get('port', 27017)
        database = self.source_config.get('database', '')

        # Get credentials (optional for MongoDB)
        username = self.source_config.get('username') or credentials.get('username_env', '')
        password = self.source_config.get('password') or credentials.get('password_env', '')

        if username and username == credentials.get('username_env', ''):
            username = self._get_env_credential(username)
        if password and password == credentials.get('password_env', ''):
            password = self._get_env_credential(password)

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_dir = os.path.join(self.dest_path, f"mongodb_{timestamp}")

        try:
            self.log(f"Starting MongoDB backup: {host}:{port}")

            # Build mongodump command
            cmd = [
                'mongodump',
                f'--host={host}',
                f'--port={port}',
                f'--out={backup_dir}'
            ]

            if username:
                cmd.extend([
                    f'--username={username}',
                    '--authenticationDatabase=admin'
                ])

            if database:
                cmd.append(f'--db={database}')

            # Add options
            options = self.source_config.get('options', {})
            if options.get('gzip', True):
                cmd.append('--gzip')

            if password:
                with mongodb_password_file(password) as config_file:
                    result = subprocess.run(
                        cmd + [f'--config={config_file}'],
                        capture_output=True,
                        text=True,
                        timeout=3600,
                    )
            else:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=3600,
                )

            if result.returncode != 0:
                raise Exception(f"mongodump failed: {result.stderr}")

            if result.stdout:
                self.log(result.stdout)

            size = self._get_directory_size(backup_dir)
            self.log(f"MongoDB backup completed: {backup_dir} ({size} bytes)")

            return {
                'files_synced': 1,
                'size_synced': size,
                'logs': self.get_logs()
            }

        except subprocess.TimeoutExpired:
            self.log("ERROR: MongoDB backup timeout")
            raise Exception("MongoDB backup timeout")
        except Exception as e:
            self.log(f"ERROR: {str(e)}")
            raise


class RedisBackup(BackupHandler):
    """Redis backup handler using RDB snapshot"""

    def backup(self):
        """Execute Redis backup"""
        host = self.source_config.get('host', 'localhost')
        port = self.source_config.get('port', 6379)
        credentials = self.source_config.get('credentials', {})

        # Get password if needed
        password = self.source_config.get('password') or credentials.get('password_env', '')
        if password and password == credentials.get('password_env', ''):
            password = self._get_env_credential(password, required=False)

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_file = os.path.join(self.dest_path, f"redis_{timestamp}.rdb")

        try:
            self.log(f"Starting Redis backup: {host}:{port}")

            # redis-cli can stream a consistent RDB snapshot from a remote
            # server directly to a local file. Reading CONFIG GET dir and then
            # copying that path only works when Redis shares this filesystem.
            cmd = ['redis-cli', '-h', host, '-p', str(port)]
            env = os.environ.copy()
            if password:
                env['REDISCLI_AUTH'] = password

            result = subprocess.run(
                cmd + ['--rdb', backup_file],
                capture_output=True,
                text=True,
                env=env,
                timeout=300,
            )

            if result.returncode != 0:
                raise Exception(f"Redis RDB transfer failed: {result.stderr[:500]}")
            size = self._get_file_size(backup_file)
            if size <= 0:
                raise Exception("Redis returned an empty RDB backup")

            self.log(f"Redis backup completed: {backup_file} ({size} bytes)")
            return {
                'files_synced': 1,
                'size_synced': size,
                'logs': self.get_logs()
            }

        except subprocess.TimeoutExpired:
            self.log("ERROR: Redis backup timeout")
            raise Exception("Redis backup timeout")
        except Exception as e:
            self.log(f"ERROR: {str(e)}")
            raise


class SQLiteBackup(BackupHandler):
    """SQLite backup handler using file copy"""

    def backup(self):
        """Execute SQLite backup"""
        source_files = self._as_list(self.source_config.get('databases'))
        if not source_files and self.source_config.get('path'):
            source_files = [self.source_config.get('path')]

        if not source_files:
            raise Exception("No SQLite database files specified")

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        total_size = 0
        files_backed_up = 0

        try:
            for db_file in source_files:
                if not os.path.exists(db_file):
                    self.log(f"ERROR: Database file not found: {db_file}")
                    continue

                self.log(f"Backing up SQLite database: {db_file}")

                db_name = os.path.basename(db_file)
                backup_file = os.path.join(
                    self.dest_path,
                    f"{db_name}_{timestamp}.db"
                )

                source_uri = Path(db_file).resolve().as_uri() + '?mode=ro'
                with closing(
                    sqlite3.connect(source_uri, uri=True, timeout=30)
                ) as source_db:
                    with closing(
                        sqlite3.connect(backup_file, timeout=30)
                    ) as backup_db:
                        source_db.backup(backup_db)
                        quick_check = backup_db.execute('PRAGMA quick_check').fetchone()
                        if not quick_check or quick_check[0] != 'ok':
                            raise Exception(
                                f"SQLite backup integrity check failed: {quick_check}"
                            )

                size = self._get_file_size(backup_file)
                total_size += size
                files_backed_up += 1

                self.log(f"SQLite backup completed: {backup_file} ({size} bytes)")

            return {
                'files_synced': files_backed_up,
                'size_synced': total_size,
                'logs': self.get_logs()
            }

        except Exception as e:
            self.log(f"ERROR: {str(e)}")
            raise


class CouchDBBackup(BackupHandler):
    """CouchDB backup handler using replication"""

    def backup(self):
        """Execute CouchDB backup"""
        host = self.source_config.get('host', 'localhost')
        port = self.source_config.get('port', 5984)
        databases = self._as_list(self.source_config.get('databases'))
        if not databases and self.source_config.get('database'):
            databases = [self.source_config.get('database')]
        credentials = self.source_config.get('credentials', {})

        # Get credentials
        username = self.source_config.get('username') or self._get_env_credential(credentials.get('username_env', 'COUCHDB_USER'))
        password = self.source_config.get('password') or self._get_env_credential(credentials.get('password_env', 'COUCHDB_PASSWORD'))

        if not databases:
            raise Exception("No CouchDB databases specified")

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        total_size = 0
        files_backed_up = 0

        try:
            for db in databases:
                self.log(f"Backing up CouchDB database: {db}")

                backup_file = os.path.join(self.dest_path, f"couchdb_{db}_{timestamp}.json")

                url = (
                    f"http://{host}:{port}/{quote(str(db), safe='')}/"
                    '_all_docs?include_docs=true'
                )
                with requests.get(
                    url,
                    auth=(username, password),
                    stream=True,
                    timeout=(10, 3600),
                ) as response:
                    response.raise_for_status()
                    with open(backup_file, 'wb') as file:
                        for chunk in response.iter_content(chunk_size=1024 * 1024):
                            if chunk:
                                file.write(chunk)

                size = self._get_file_size(backup_file)
                total_size += size
                files_backed_up += 1

                self.log(f"CouchDB backup completed: {backup_file} ({size} bytes)")

            return {
                'files_synced': files_backed_up,
                'size_synced': total_size,
                'logs': self.get_logs()
            }

        except subprocess.TimeoutExpired:
            self.log("ERROR: CouchDB backup timeout")
            raise Exception("CouchDB backup timeout")
        except Exception as e:
            self.log(f"ERROR: {str(e)}")
            raise


class InfluxDBBackup(BackupHandler):
    """InfluxDB 2.x backup handler using influx CLI"""

    def backup(self):
        """Execute InfluxDB backup"""
        host = self.source_config.get('host', 'localhost')
        port = self.source_config.get('port', 8086)
        credentials = self.source_config.get('credentials', {})

        # Get token from environment
        token = self.source_config.get('token') or self._get_env_credential(
            credentials.get('token_env', 'INFLUXDB_TOKEN')
        )

        org = self.source_config.get('org', '')
        bucket = self.source_config.get('bucket', '')

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_dir = os.path.join(self.dest_path, f"influxdb_{timestamp}")
        os.makedirs(backup_dir, exist_ok=True)

        try:
            self.log(f"Starting InfluxDB backup: {host}:{port}")

            # Build influx backup command (InfluxDB 2.x)
            cmd = [
                'influx', 'backup',
                backup_dir,
                '--host', f'http://{host}:{port}',
            ]
            process_env = os.environ.copy()
            process_env['INFLUX_TOKEN'] = token

            if org:
                cmd.extend(['--org', org])
            if bucket:
                cmd.extend(['--bucket', bucket])

            # Execute backup
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=3600,
                env=process_env,
            )

            if result.returncode != 0:
                raise Exception(f"influx backup failed: {result.stderr}")

            if result.stdout:
                self.log(result.stdout)

            # Compress backup directory
            options = self.source_config.get('options', {})
            if options.get('compress', True):
                self.log("Compressing InfluxDB backup...")
                archive = os.path.join(self.dest_path, f"influxdb_{timestamp}.tar.gz")
                subprocess.run(
                    ['tar', 'czf', archive, '-C', self.dest_path, f"influxdb_{timestamp}"],
                    check=True, timeout=600
                )
                shutil.rmtree(backup_dir)
                size = self._get_file_size(archive)
            else:
                size = self._get_directory_size(backup_dir)

            self.log(f"InfluxDB backup completed: {size} bytes")

            return {
                'files_synced': 1,
                'size_synced': size,
                'logs': self.get_logs()
            }

        except subprocess.TimeoutExpired:
            self.log("ERROR: InfluxDB backup timeout")
            raise Exception("InfluxDB backup timeout")
        except Exception as e:
            self.log(f"ERROR: {str(e)}")
            raise
