"""
Supabase Restore Handler
Restores a Supabase backup to a target project using psql.
Supports schema, data, and optional storage restore.
"""
import subprocess
import logging
import os
import glob
import json
import shutil
import tarfile
from datetime import datetime
from urllib.parse import quote as quote_path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from app.postgres_utils import safe_postgres_command

logger = logging.getLogger(__name__)


def _safe_extract(tar, destination):
    """Extract regular files/directories without links or special devices."""
    real_destination = os.path.realpath(destination)
    for member in tar.getmembers():
        member_path = os.path.realpath(os.path.join(real_destination, member.name))
        try:
            inside = os.path.commonpath((real_destination, member_path)) == real_destination
        except ValueError:
            inside = False
        if not inside:
            raise ValueError(f"Unsicherer Archivpfad: {member.name}")
        if member.issym() or member.islnk():
            raise ValueError(f"Archiv-Links sind nicht erlaubt: {member.name}")
        if member.isdev() or member.isfifo():
            raise ValueError(f"Spezialdateien sind nicht erlaubt: {member.name}")
    tar.extractall(destination, filter='data')


class SupabaseRestore:
    """Restore Supabase backups to a target project"""

    def __init__(self):
        self.logs = []
        self._status_callback = None

    def log(self, message):
        timestamp = datetime.now().strftime('%H:%M:%S')
        entry = f"[{timestamp}] {message}"
        self.logs.append(entry)
        logger.info(message)
        if self._status_callback:
            try:
                self._status_callback(self.get_logs())
            except Exception:
                logger.exception('Could not persist restore progress')

    def get_logs(self):
        """Get all log entries as string"""
        return '\n'.join(self.logs)

    def restore(self, backup_path, target_config):
        """
        Restore backup to target Supabase project.

        Args:
            backup_path: Path to backup directory or .tar.gz archive
            target_config: dict with optional 'profile' (credential profile name) and/or
                          target_connection_string, target_db_password,
                          target_service_role_key (override profile values)
        Returns:
            dict with status, logs
        """
        from urllib.parse import quote, unquote
        import re
        from app.api.settings import get_credential

        profile = target_config.get('profile') or None
        target_conn = (target_config.get('target_connection_string') or '').strip()
        target_password = target_config.get('target_db_password') or ''
        restore_storage = target_config.get('restore_storage', False)
        target_service_key = target_config.get('target_service_role_key') or ''

        # Fallback: fetch missing values from credential profile
        if not target_conn:
            target_conn = get_credential('supabase_connection_string', profile=profile) or ''
        if not target_password:
            target_password = get_credential('supabase_db_password', profile=profile) or ''
        if restore_storage and not target_service_key:
            target_service_key = get_credential('supabase_service_role_key', profile=profile) or ''

        if not target_conn:
            raise Exception("Connection String fehlt. Wähle ein Profil oder gib einen Connection String an.")

        # Decode URL-encoded brackets from Supabase Dashboard
        target_conn = unquote(target_conn)

        # Replace [YOUR-PASSWORD] placeholder
        if '[YOUR-PASSWORD]' in target_conn:
            if not target_password:
                raise Exception("target_db_password required when [YOUR-PASSWORD] placeholder used")
            target_conn = target_conn.replace('[YOUR-PASSWORD]', quote(target_password, safe=''))

        # Extract target ref for storage restore
        match = re.search(r'postgres\.([a-z0-9-]+)[:@]', target_conn) or re.search(r'db\.([a-z0-9-]+)\.supabase', target_conn)
        target_ref = match.group(1) if match else ''

        # Handle tar.gz archives
        working_dir = backup_path
        temp_extracted = False

        if backup_path.endswith('.tar.gz'):
            self.log("Entpacke Backup-Archiv...")
            import tempfile
            archive_parent = os.path.dirname(os.path.realpath(backup_path))
            archive_name = os.path.basename(backup_path)[:-7]
            extract_dir = tempfile.mkdtemp(
                prefix=f'.{archive_name}_',
                suffix='_restore_tmp',
                dir=archive_parent,
            )
            temp_extracted = True
            try:
                with tarfile.open(backup_path, 'r:gz') as tar:
                    _safe_extract(tar, extract_dir)
                # Find the actual backup dir inside
                subdirs = [d for d in os.listdir(extract_dir)
                           if os.path.isdir(os.path.join(extract_dir, d))]
                if len(subdirs) == 1:
                    working_dir = os.path.join(extract_dir, subdirs[0])
                else:
                    working_dir = extract_dir
                # A run archive (<source>_<timestamp>.tar.gz) wraps the
                # handler's own supabase_<ref>_<timestamp>.tar.gz.
                working_dir = self._unwrap_nested_archive(working_dir, extract_dir)
            except Exception:
                shutil.rmtree(extract_dir, ignore_errors=True)
                temp_extracted = False
                raise

        total_steps = 0
        completed_steps = 0
        errors = []

        try:
            # 1. Restore Schema
            schema_files = sorted(glob.glob(os.path.join(working_dir, 'schema_*.sql')))
            if schema_files:
                total_steps += 1
                self.log(f"Stelle Schema wieder her: {os.path.basename(schema_files[0])}")
                result = self._run_psql(target_conn, schema_files[0])
                if result['success']:
                    completed_steps += 1
                    self.log("Schema wiederhergestellt ✓")
                else:
                    errors.append(f"Schema: {result['error']}")
                    self.log(f"ERROR: Schema-Restore fehlgeschlagen: {result['error']}")

            # 2. Restore Data
            data_files = sorted(glob.glob(os.path.join(working_dir, 'data_*.sql')))
            if data_files:
                total_steps += 1
                self.log(f"Stelle Daten wieder her: {os.path.basename(data_files[0])}")
                result = self._run_psql(target_conn, data_files[0])
                if result['success']:
                    completed_steps += 1
                    self.log("Daten wiederhergestellt ✓")
                else:
                    errors.append(f"Data: {result['error']}")
                    self.log(f"ERROR: Daten-Restore fehlgeschlagen: {result['error']}")

            # 3. Restore Roles (optional, may fail due to permissions)
            roles_files = sorted(glob.glob(os.path.join(working_dir, 'roles_*.sql')))
            if roles_files:
                total_steps += 1
                self.log(f"Stelle Roles wieder her: {os.path.basename(roles_files[0])}")
                result = self._run_psql(target_conn, roles_files[0])
                if result['success']:
                    completed_steps += 1
                    self.log("Roles wiederhergestellt ✓")
                else:
                    errors.append(f"Roles: {result['error']}")
                    self.log(f"WARNING: Roles-Restore fehlgeschlagen: {result['error']}")

            # 4. Restore Auth/Config (optional)
            config_dir = os.path.join(working_dir, 'config')
            if os.path.isdir(config_dir):
                auth_files = sorted(glob.glob(os.path.join(config_dir, 'auth_schema_*.sql')))
                if auth_files:
                    total_steps += 1
                    self.log(f"Stelle Auth-Schema wieder her...")
                    result = self._run_psql(target_conn, auth_files[0])
                    if result['success']:
                        completed_steps += 1
                        self.log("Auth-Schema wiederhergestellt ✓")
                    else:
                        errors.append(f"Auth-Schema: {result['error']}")
                        self.log(f"WARNING: Auth-Schema-Restore: {result['error']}")

            # 5. Storage Restore (optional)
            storage_dir = os.path.join(working_dir, 'storage')
            if restore_storage:
                total_steps += 1
                if not os.path.isdir(storage_dir):
                    errors.append('Storage: Kein Storage-Backup gefunden')
                    self.log('ERROR: Kein Storage-Backup gefunden')
                elif not target_service_key:
                    errors.append('Storage: Service Role Key fehlt')
                    self.log('ERROR: Service Role Key für Storage-Restore fehlt')
                elif not target_ref:
                    errors.append('Storage: Project Ref konnte nicht ermittelt werden')
                    self.log('ERROR: Project Ref konnte aus dem Ziel-Connection-String nicht gelesen werden')
                else:
                    self.log("Stelle Storage-Objekte wieder her...")
                    try:
                        storage_result = self._restore_storage(
                            storage_dir, target_ref, target_service_key
                        )
                        completed_steps += 1
                        self.log(f"Storage wiederhergestellt: {storage_result['files']} Dateien ✓")
                        if storage_result.get('failed'):
                            errors.append(
                                f"Storage: {storage_result['failed']} Uploads fehlgeschlagen"
                            )
                    except Exception as e:
                        errors.append(f"Storage: {str(e)}")
                        self.log(f"ERROR: Storage-Restore fehlgeschlagen: {e}")

            if total_steps == 0:
                raise ValueError('Backup enthält keine wiederherstellbaren Artefakte')

            status = 'completed' if not errors else 'partial'
            self.log(f"Restore abgeschlossen: {completed_steps}/{total_steps} Schritte, Status: {status}")

            return {
                'status': status,
                'steps_total': total_steps,
                'steps_completed': completed_steps,
                'errors': errors,
                'logs': self.get_logs()
            }

        finally:
            # Cleanup temp extraction
            if temp_extracted and os.path.isdir(extract_dir):
                shutil.rmtree(extract_dir, ignore_errors=True)

    def _unwrap_nested_archive(self, working_dir, extract_dir):
        """Extract a single inner tar.gz when the dump files are not at top level."""
        if glob.glob(os.path.join(working_dir, 'schema_*.sql')):
            return working_dir
        inner = [
            name for name in os.listdir(working_dir)
            if name.endswith('.tar.gz') and not name.startswith('.')
        ]
        if len(inner) != 1:
            return working_dir
        inner_dir = os.path.join(extract_dir, '_inner')
        os.makedirs(inner_dir)
        with tarfile.open(os.path.join(working_dir, inner[0]), 'r:gz') as tar:
            _safe_extract(tar, inner_dir)
        subdirs = [d for d in os.listdir(inner_dir)
                   if os.path.isdir(os.path.join(inner_dir, d))]
        if len(subdirs) == 1:
            return os.path.join(inner_dir, subdirs[0])
        return inner_dir

    def _run_psql(self, connection_string, sql_file, timeout=3600):
        """Run psql with a SQL file against connection"""
        try:
            safe_connection, env = safe_postgres_command(connection_string)
        except ValueError as exc:
            return {'success': False, 'error': str(exc)}
        try:
            result = subprocess.run(
                ['psql', safe_connection, '-f', sql_file,
                 '--set', 'ON_ERROR_STOP=on'],
                capture_output=True, text=True, env=env, timeout=timeout
            )

            stderr = result.stderr.strip()
            serious_errors = [
                line for line in stderr.splitlines()
                if 'ERROR:' in line.upper() or 'FATAL:' in line.upper()
            ]
            if result.returncode != 0 or serious_errors:
                error_lines = serious_errors or stderr.splitlines()
                message = '\n'.join(error_lines[:5]).strip()
                return {
                    'success': False,
                    'error': message or f'psql exited with code {result.returncode}',
                }
            return {'success': True, 'output': result.stdout}

        except subprocess.TimeoutExpired:
            return {'success': False, 'error': f'Timeout nach {timeout}s'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def _restore_storage(self, storage_dir, target_ref, service_role_key):
        """Upload storage objects to target project"""
        api_url = f"https://{target_ref}.supabase.co"
        headers = {
            'Authorization': f'Bearer {service_role_key}',
            'apikey': service_role_key,
        }

        files_uploaded = 0
        files_failed = 0
        upload_errors = []
        metadata_root = os.path.join(os.path.dirname(storage_dir), 'storage_metadata')
        has_new_metadata = os.path.isdir(metadata_root)

        # Iterate buckets
        for bucket_name in os.listdir(storage_dir):
            bucket_path = os.path.join(storage_dir, bucket_name)
            if not os.path.isdir(bucket_path):
                continue

            self.log(f"Upload Bucket: {bucket_name}")

            bucket_meta = self._load_bucket_metadata(
                bucket_path, bucket_name, metadata_root
            )
            if bucket_meta:
                self._create_bucket(api_url, headers, bucket_meta)

            object_metadata = self._load_object_metadata(bucket_name, metadata_root)

            # Upload files
            for root, dirs, files in os.walk(bucket_path):
                for filename in files:
                    if filename == '_bucket_meta.json' and not has_new_metadata:
                        continue

                    filepath = os.path.join(root, filename)
                    # Calculate relative path within bucket
                    rel_path = os.path.relpath(filepath, bucket_path)
                    rel_path = rel_path.replace(os.sep, '/')

                    try:
                        self._upload_file(
                            api_url,
                            headers,
                            bucket_name,
                            rel_path,
                            filepath,
                            object_metadata.get(rel_path, {})
                        )
                        files_uploaded += 1
                    except Exception as e:
                        files_failed += 1
                        upload_errors.append(f"{bucket_name}/{rel_path}: {e}")
                        self.log(f"WARNING: Upload fehlgeschlagen {rel_path}: {e}")

        return {
            'files': files_uploaded,
            'failed': files_failed,
            'errors': upload_errors,
        }

    def _create_bucket(self, api_url, headers, bucket_meta):
        """Create a bucket on target (ignore if exists)"""
        body = json.dumps({
            'id': bucket_meta.get('id', ''),
            'name': bucket_meta.get('name', ''),
            'public': bucket_meta.get('public', False),
        }).encode('utf-8')

        req = Request(
            f"{api_url}/storage/v1/bucket",
            data=body,
            headers={**headers, 'Content-Type': 'application/json'},
            method='POST'
        )

        try:
            # api_url is always HTTPS and derived from a validated project ref.
            with urlopen(req, timeout=30) as resp:  # nosec B310
                pass  # Created
        except HTTPError as e:
            if e.code in (409, 400):
                pass  # Already exists (Supabase returns 400 or 409)
            else:
                self.log(f"WARNING: Bucket-Erstellung: {e}")

    def _upload_file(self, api_url, headers, bucket_id, object_path, local_path, object_meta=None):
        """Upload a file to Supabase Storage"""
        with open(local_path, 'rb') as f:
            file_data = f.read()

        upload_headers = {
            **headers,
            **self._storage_upload_headers(object_meta or {}),
            'x-upsert': 'true',
        }

        req = Request(
            f"{api_url}/storage/v1/object/{bucket_id}/"
            f"{quote_path(object_path, safe='/')}",
            data=file_data,
            headers=upload_headers,
            method='POST'
        )

        # api_url is always HTTPS and derived from a validated project ref.
        with urlopen(req, timeout=120) as resp:  # nosec B310
            pass

    def _load_bucket_metadata(self, bucket_path, bucket_name, metadata_root):
        """Read new metadata layout first, then legacy metadata inside bucket."""
        meta_file = os.path.join(
            metadata_root, 'buckets', self._metadata_filename(bucket_name)
        )
        data = self._read_json(meta_file)
        if data:
            return data

        legacy_meta_file = os.path.join(bucket_path, '_bucket_meta.json')
        return self._read_json(legacy_meta_file)

    def _load_object_metadata(self, bucket_name, metadata_root):
        """Read object metadata saved during backup."""
        meta_file = os.path.join(
            metadata_root, 'objects', self._metadata_filename(bucket_name)
        )
        return self._read_json(meta_file) or {}

    def _read_json(self, path):
        if not path or not os.path.exists(path):
            return None
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            self.log(f"WARNING: Metadaten konnten nicht gelesen werden {path}: {e}")
            return None

    def _metadata_filename(self, value):
        """Return a filesystem-safe metadata filename for bucket scoped data."""
        return f"{quote_path(value or 'bucket', safe='')}.json"

    def _storage_upload_headers(self, object_meta):
        """Preserve common Supabase Storage object metadata on upload."""
        metadata = object_meta.get('metadata') or {}
        content_type = (
            metadata.get('mimetype')
            or metadata.get('contentType')
            or metadata.get('content_type')
            or object_meta.get('mimetype')
            or object_meta.get('contentType')
            or 'application/octet-stream'
        )
        cache_control = (
            metadata.get('cacheControl')
            or metadata.get('cache_control')
            or object_meta.get('cacheControl')
            or object_meta.get('cache_control')
        )

        headers = {'Content-Type': content_type}
        if cache_control:
            headers['cache-control'] = str(cache_control)
        return headers
