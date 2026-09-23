"""
Supabase Backup Handler
Supports two modes:
- "full": DB (roles, schema, data) + Storage Buckets + Projekt-Config
- "db_only": Only PostgreSQL dump (roles, schema, data)

Uses pg_dump directly for database backups.
Storage objects are downloaded via Supabase Storage API.
"""
import subprocess
import logging
import os
import json
import shutil
from datetime import datetime
from urllib.parse import quote as quote_path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from app.backup.base import BackupHandler
from app.postgres_utils import safe_postgres_command

logger = logging.getLogger(__name__)


class SupabaseBackup(BackupHandler):
    """Supabase backup handler with full and db_only modes"""

    def backup(self):
        """Execute Supabase backup"""
        backup_mode = self.source_config.get('backup_mode', 'db_only')
        options = self.source_config.get('options', {})

        # Get all credentials from profile (provider-based)
        from app.api.settings import get_credential
        profile = self.source_config.get('credential_profile')

        connection_string = (
            self.source_config.get('connection_string', '')
            or get_credential('supabase_connection_string', profile=profile)
        )
        if not connection_string:
            raise Exception("Connection String fehlt. Wähle ein Supabase-Profil mit konfiguriertem Connection String.")

        # Decode URL-encoded brackets from Supabase Dashboard
        from urllib.parse import unquote, quote
        connection_string = unquote(connection_string)

        # Replace [YOUR-PASSWORD] placeholder
        if '[YOUR-PASSWORD]' in connection_string:
            db_password = get_credential('supabase_db_password', profile=profile)
            if not db_password:
                raise Exception("DB Passwort fehlt im Profil. Trage es in den Credentials ein.")
            connection_string = connection_string.replace('[YOUR-PASSWORD]', quote(db_password, safe=''))

        # Extract project_ref from connection string for API URL
        project_ref = self._extract_project_ref(connection_string)
        if backup_mode == 'full' and not project_ref:
            raise Exception("Project Ref konnte aus dem Connection String nicht ermittelt werden.")

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_dir = os.path.join(self.dest_path, f"supabase_{timestamp}")
        os.makedirs(backup_dir, exist_ok=True)

        total_size = 0
        files_backed_up = 0

        try:
            # --- Database Backup (always) ---
            db_size, db_files = self._backup_database(
                connection_string, backup_dir, timestamp, options
            )
            total_size += db_size
            files_backed_up += db_files

            # --- Full mode: Storage + Config ---
            if backup_mode == 'full':
                service_role_key = (
                    self.source_config.get('service_role_key', '')
                    or get_credential('supabase_service_role_key', profile=profile)
                )
                if not service_role_key:
                    raise Exception("Service Role Key fehlt für Supabase Full Backup.")

                api_url = f"https://{project_ref}.supabase.co"

                if options.get('include_storage', True):
                    storage_size, storage_files = self._backup_storage(
                        api_url, service_role_key, backup_dir
                    )
                    total_size += storage_size
                    files_backed_up += storage_files

                if options.get('include_auth_config', True):
                    config_size, config_files = self._backup_config(
                        connection_string, backup_dir, timestamp
                    )
                    total_size += config_size
                    files_backed_up += config_files

            # Compress if requested
            if options.get('compress', True):
                self.log("Komprimiere Backup...")
                archive = os.path.join(
                    self.dest_path, f"supabase_{project_ref}_{timestamp}.tar.gz"
                )
                subprocess.run(
                    ['tar', 'czf', archive, '-C', self.dest_path,
                     f"supabase_{timestamp}"],
                    check=True, timeout=600
                )
                shutil.rmtree(backup_dir)
                total_size = self._get_file_size(archive)
                self.log(f"Backup komprimiert: {archive}")

            self.log(
                f"Supabase Backup abgeschlossen: "
                f"{files_backed_up} Dateien, {total_size} Bytes"
            )

            return {
                'files_synced': files_backed_up,
                'size_synced': total_size,
                'logs': self.get_logs()
            }

        except subprocess.TimeoutExpired:
            self.log("ERROR: Supabase Backup Timeout")
            raise Exception("Supabase backup timeout")
        except Exception as e:
            self.log(f"ERROR: {str(e)}")
            raise

    def _backup_database(self, connection_string, backup_dir, timestamp, options):
        """
        Backup PostgreSQL database in three parts: roles, schema, data.
        Returns (total_size, file_count).
        """
        total_size = 0
        files = 0
        timeout = options.get('timeout', 3600)

        safe_connection, env = safe_postgres_command(connection_string)

        # 1. Roles dump
        roles_file = os.path.join(backup_dir, f"roles_{timestamp}.sql")
        self.log("Dumping roles...")
        result = subprocess.run(
            ['pg_dumpall', '--dbname', safe_connection,
             '--roles-only', '-f', roles_file],
            capture_output=True, text=True, env=env, timeout=timeout
        )
        if result.returncode != 0:
            self.log(f"ERROR: Roles dump returned code {result.returncode}: "
                     f"{result.stderr}")
        else:
            total_size += self._get_file_size(roles_file)
            files += 1
            self.log(f"Roles dump: {roles_file}")

        # 2. Schema dump
        schema_file = os.path.join(backup_dir, f"schema_{timestamp}.sql")
        self.log("Dumping schema...")
        result = subprocess.run(
            ['pg_dump', safe_connection,
             '--schema-only', '-f', schema_file],
            capture_output=True, text=True, env=env, timeout=timeout
        )
        if result.returncode != 0:
            raise Exception(f"Schema dump failed: {result.stderr}")
        total_size += self._get_file_size(schema_file)
        files += 1
        self.log(f"Schema dump: {schema_file}")

        # 3. Data dump
        data_file = os.path.join(backup_dir, f"data_{timestamp}.sql")
        self.log("Dumping data (COPY format)...")
        data_cmd = ['pg_dump', safe_connection, '--data-only',
                    '-f', data_file]
        result = subprocess.run(
            data_cmd,
            capture_output=True, text=True, env=env, timeout=timeout
        )
        if result.returncode != 0:
            raise Exception(f"Data dump failed: {result.stderr}")
        total_size += self._get_file_size(data_file)
        files += 1
        self.log(f"Data dump: {data_file}")

        return total_size, files

    def _backup_storage(self, api_url, service_role_key, backup_dir):
        """
        Backup all Storage buckets and their objects.
        Returns (total_size, file_count).
        """
        storage_dir = os.path.join(backup_dir, 'storage')
        metadata_dir = os.path.join(backup_dir, 'storage_metadata')
        bucket_metadata_dir = os.path.join(metadata_dir, 'buckets')
        object_metadata_dir = os.path.join(metadata_dir, 'objects')
        os.makedirs(storage_dir, exist_ok=True)
        os.makedirs(bucket_metadata_dir, exist_ok=True)
        os.makedirs(object_metadata_dir, exist_ok=True)

        total_size = 0
        files = 0
        headers = {
            'Authorization': f'Bearer {service_role_key}',
            'apikey': service_role_key,
        }

        # List all buckets
        self.log("Listing Storage Buckets...")
        buckets = self._api_get(f"{api_url}/storage/v1/bucket", headers)

        if not buckets:
            self.log("Keine Storage Buckets gefunden.")
            return 0, 0

        for bucket in buckets:
            bucket_id = bucket.get('id', '')
            bucket_name = bucket.get('name', bucket_id)
            self.log(f"Backup Bucket: {bucket_name}")

            bucket_dir = os.path.join(storage_dir, bucket_name)
            os.makedirs(bucket_dir, exist_ok=True)

            meta_name = self._metadata_filename(bucket_name)
            bucket_meta_file = os.path.join(bucket_metadata_dir, meta_name)
            with open(bucket_meta_file, 'w', encoding='utf-8') as f:
                json.dump(bucket, f, indent=2)

            # List objects in bucket
            objects = self._list_bucket_objects(
                api_url, headers, bucket_id
            )
            object_metadata = {}

            for obj in objects:
                obj_name = obj.get('name', '')
                if not obj_name or obj.get('id') is None:
                    continue

                try:
                    obj_path = self._safe_storage_path(bucket_dir, obj_name)
                    obj_dir = os.path.dirname(obj_path)
                    os.makedirs(obj_dir, exist_ok=True)

                    # Download object
                    download_url = (
                        f"{api_url}/storage/v1/object/{bucket_id}/"
                        f"{quote_path(obj_name, safe='/')}"
                    )
                    self._download_file(download_url, headers, obj_path)

                    size = self._get_file_size(obj_path)
                    total_size += size
                    files += 1
                    object_metadata[obj_name] = self._extract_object_metadata(obj)
                except Exception as e:
                    self.log(f"ERROR: Konnte {obj_name} nicht laden: {e}")

            objects_meta_file = os.path.join(object_metadata_dir, meta_name)
            with open(objects_meta_file, 'w', encoding='utf-8') as f:
                json.dump(object_metadata, f, indent=2)

        self.log(f"Storage Backup: {files} Dateien, {total_size} Bytes")
        return total_size, files

    def _list_bucket_objects(self, api_url, headers, bucket_id,
                             prefix='', limit=1000):
        """Recursively list all objects in a bucket."""
        all_objects = []
        offset = 0

        while True:
            body = json.dumps({
                'prefix': prefix,
                'limit': limit,
                'offset': offset,
            }).encode('utf-8')

            req = Request(
                f"{api_url}/storage/v1/object/list/{bucket_id}",
                data=body,
                headers={**headers, 'Content-Type': 'application/json'},
                method='POST'
            )

            try:
                # api_url is always HTTPS and derived from a validated project ref.
                with urlopen(req, timeout=30) as resp:  # nosec B310
                    items = json.loads(resp.read().decode('utf-8'))
            except Exception as e:
                self.log(f"ERROR: Bucket-Listing fehlgeschlagen: {e}")
                raise

            if not items:
                break

            for item in items:
                if item.get('id') is None:
                    # Folder - recurse
                    folder_prefix = prefix + item.get('name', '') + '/'
                    sub_items = self._list_bucket_objects(
                        api_url, headers, bucket_id, folder_prefix, limit
                    )
                    all_objects.extend(sub_items)
                else:
                    # File
                    item['name'] = prefix + item.get('name', '')
                    all_objects.append(item)

            if len(items) < limit:
                break
            offset += limit

        return all_objects

    def _backup_config(self, connection_string, backup_dir, timestamp):
        """
        Backup RLS policies and auth config via SQL queries.
        Returns (total_size, file_count).
        """
        config_dir = os.path.join(backup_dir, 'config')
        os.makedirs(config_dir, exist_ok=True)

        total_size = 0
        files = 0
        safe_connection, env = safe_postgres_command(connection_string)

        # Dump RLS policies (no trailing semicolon — \copy doesn't allow it)
        rls_file = os.path.join(config_dir, f"rls_policies_{timestamp}.sql")
        rls_query = (
            "SELECT schemaname, tablename, policyname, permissive, roles, cmd, qual, with_check "
            "FROM pg_policies "
            "ORDER BY schemaname, tablename, policyname"
        )
        self.log("Exporting RLS Policies...")
        result = subprocess.run(
            ['psql', safe_connection, '-c',
             f"\\copy ({rls_query}) TO STDOUT WITH CSV HEADER"],
            capture_output=True, text=True, env=env, timeout=120
        )

        if result.returncode == 0 and result.stdout:
            with open(rls_file, 'w') as f:
                f.write(result.stdout)
            total_size += self._get_file_size(rls_file)
            files += 1
            self.log(f"RLS Policies exportiert: {rls_file}")
        else:
            self.log(f"ERROR: RLS Policy Export: {result.stderr}")

        # Dump auth schema
        auth_file = os.path.join(config_dir, f"auth_schema_{timestamp}.sql")
        self.log("Exporting auth schema...")
        result = subprocess.run(
            ['pg_dump', safe_connection,
             '--schema=auth', '--schema=storage',
             '-f', auth_file],
            capture_output=True, text=True, env=env, timeout=300
        )

        if result.returncode == 0:
            total_size += self._get_file_size(auth_file)
            files += 1
            self.log(f"Auth/Storage Schema exportiert: {auth_file}")
        else:
            self.log(f"ERROR: Auth Schema Export: {result.stderr}")

        return total_size, files

    def _extract_project_ref(self, connection_string):
        """Extract project ref from connection string.
        Handles both formats:
        - pooler: postgres.PROJECTREF@...pooler.supabase.com
        - direct: @db.PROJECTREF.supabase.co
        """
        import re
        # Try pooler format: postgres.XXXXX:
        match = re.search(r'postgres\.([a-z0-9-]+)[:@]', connection_string)
        if match:
            return match.group(1)
        # Try direct format: db.XXXXX.supabase
        match = re.search(r'db\.([a-z0-9-]+)\.supabase', connection_string)
        if match:
            return match.group(1)
        return ''

    def _api_get(self, url, headers):
        """Simple GET request, returns parsed JSON or empty list."""
        req = Request(url, headers=headers, method='GET')
        try:
            # URLs are derived from the HTTPS Supabase API base.
            with urlopen(req, timeout=30) as resp:  # nosec B310
                return json.loads(resp.read().decode('utf-8'))
        except (HTTPError, URLError) as e:
            self.log(f"ERROR: API GET fehlgeschlagen: {e}")
            raise

    def _download_file(self, url, headers, dest_path):
        """Download file from URL to dest_path."""
        req = Request(url, headers=headers, method='GET')
        # URLs are derived from the HTTPS Supabase API base.
        with urlopen(req, timeout=120) as resp:  # nosec B310
            with open(dest_path, 'wb') as f:
                shutil.copyfileobj(resp, f)

    def _metadata_filename(self, value):
        """Return a filesystem-safe metadata filename for bucket scoped data."""
        return f"{quote_path(value or 'bucket', safe='')}.json"

    def _safe_storage_path(self, bucket_dir, object_name):
        """Map a Storage object key to disk without allowing path traversal."""
        real_bucket_dir = os.path.realpath(bucket_dir)
        real_target = os.path.realpath(os.path.join(bucket_dir, object_name))
        try:
            inside = os.path.commonpath((real_bucket_dir, real_target)) == real_bucket_dir
        except ValueError:
            inside = False
        if not inside or real_target == real_bucket_dir:
            raise Exception(f"Unsicherer Storage-Objektpfad: {object_name}")
        return real_target

    def _extract_object_metadata(self, obj):
        """Keep Supabase object metadata needed for a closer restore."""
        return {
            'name': obj.get('name'),
            'id': obj.get('id'),
            'updated_at': obj.get('updated_at'),
            'created_at': obj.get('created_at'),
            'last_accessed_at': obj.get('last_accessed_at'),
            'metadata': obj.get('metadata') or {},
        }
