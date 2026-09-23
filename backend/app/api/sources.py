"""
Sources API Endpoints
"""
from flask import Blueprint, request, jsonify
import logging
import requests

from app.api.auth import admin_required
from app import limiter
from app.backup.paths import validate_source_id
from app.scheduler.schedule import (
    describe_schedule,
    get_default_schedule,
    next_run_after,
    resolve_schedule,
    set_default_schedule,
    validate_schedule,
)
from app.services.github_discovery import discover_all
from app.source_config import (
    load_sources,
    merge_preserving_redacted,
    redact_source_secrets,
    save_sources,
)
from app.postgres_utils import safe_postgres_command
from app.runtime_settings import backup_root_path

logger = logging.getLogger(__name__)

sources_bp = Blueprint('sources', __name__)


@sources_bp.route('', methods=['GET'])
@admin_required
def get_sources(current_user):
    """Get all backup sources"""
    sources = load_sources(redact=True)
    return jsonify({'sources': sources}), 200


@sources_bp.route('/<source_id>', methods=['GET'])
@admin_required
def get_source(current_user, source_id):
    """Get a specific source"""
    sources = load_sources(redact=True)
    source = next((s for s in sources if s.get('id') == source_id), None)

    if not source:
        return jsonify({'error': 'Source not found'}), 404

    return jsonify(source), 200


@sources_bp.route('', methods=['POST'])
@admin_required
def create_source(current_user):
    """Create a new backup source"""
    data = request.get_json()

    if not isinstance(data, dict) or not data.get('name') or not data.get('type'):
        return jsonify({'error': 'Missing required fields: name, type'}), 400

    sources = load_sources()

    # Generate ID if not provided
    if not data.get('id'):
        import uuid
        data['id'] = f"{data['type']}-{str(uuid.uuid4())[:8]}"

    try:
        data['id'] = validate_source_id(data['id'])
    except ValueError as e:
        return jsonify({'error': str(e)}), 400

    # Check for duplicate ID
    if any(s.get('id') == data['id'] for s in sources):
        return jsonify({'error': 'Source ID already exists'}), 400

    # Set defaults
    data.setdefault('enabled', True)
    data.setdefault('priority', len(sources) + 1)

    if 'schedule' in data:
        schedule, error = validate_schedule(data['schedule'])
        if error:
            return jsonify({'error': error}), 400
        data['schedule'] = schedule

    sources.append(data)
    save_sources(sources)

    return jsonify({
        'message': 'Source created successfully',
        'source': redact_source_secrets(data)
    }), 201


@sources_bp.route('/<source_id>', methods=['PUT'])
@admin_required
def update_source(current_user, source_id):
    """Update a backup source"""
    try:
        validate_source_id(source_id)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400

    data = request.get_json()
    if not isinstance(data, dict):
        return jsonify({'error': 'Request body must be an object'}), 400
    sources = load_sources()

    source_index = next((i for i, s in enumerate(sources) if s.get('id') == source_id), None)

    if source_index is None:
        return jsonify({'error': 'Source not found'}), 404

    if 'schedule' in data:
        schedule, error = validate_schedule(data['schedule'])
        if error:
            return jsonify({'error': error}), 400
        data['schedule'] = schedule

    # Update source
    sources[source_index] = merge_preserving_redacted(sources[source_index], data)
    sources[source_index]['id'] = source_id  # Ensure ID doesn't change

    save_sources(sources)

    return jsonify({
        'message': 'Source updated successfully',
        'source': redact_source_secrets(sources[source_index])
    }), 200


@sources_bp.route('/<source_id>', methods=['DELETE'])
@admin_required
def delete_source(current_user, source_id):
    """Delete a backup source"""
    sources = load_sources()
    sources = [s for s in sources if s.get('id') != source_id]

    save_sources(sources)

    return jsonify({'message': 'Source deleted successfully'}), 200


def _github_error_message(response):
    """Translate a GitHub API error response into (message, http_status)."""
    if response is None:
        return 'GitHub API request failed', 502

    status = response.status_code

    if status == 401:
        return ('GitHub token is invalid or expired. Update it in '
                'Settings → Credentials.'), 401
    if status == 403:
        # 403 covers both rate limiting and missing scopes.
        if response.headers.get('X-RateLimit-Remaining') == '0':
            return ('GitHub rate limit reached. Try again later.'), 429
        return ('GitHub denied access. The token is missing the "repo" '
                'scope.'), 403
    if status == 404:
        return 'GitHub resource not found.', 404

    return f'GitHub API error ({status}).', 502


@sources_bp.route('/schedules', methods=['GET'])
@admin_required
def get_schedules(current_user):
    """List the effective schedule and next run time for every source."""
    from datetime import datetime

    default_schedule = get_default_schedule()
    now = datetime.now()  # local time, matching the scheduler
    entries = []

    for source in load_sources():
        schedule = resolve_schedule(source, default_schedule)
        next_run = next_run_after(schedule, now)
        entries.append({
            'source_id': source.get('id'),
            'source_name': source.get('name'),
            'source_enabled': source.get('enabled', True),
            'inherits_default': 'schedule' not in source,
            'schedule': schedule,
            'summary': describe_schedule(schedule),
            'next_run': next_run.isoformat() if next_run else None,
        })

    return jsonify({
        'default': default_schedule,
        'schedules': entries,
    }), 200


@sources_bp.route('/schedules/default', methods=['PUT'])
@admin_required
def update_default_schedule(current_user):
    """Update the global default schedule inherited by sources without one."""
    data = request.get_json() or {}
    schedule, error = validate_schedule(data)
    if error:
        return jsonify({'error': error}), 400

    saved = set_default_schedule(schedule)
    return jsonify({
        'message': 'Default schedule updated',
        'schedule': saved,
        'summary': describe_schedule(saved),
    }), 200


@sources_bp.route('/github/discover', methods=['GET'])
@admin_required
@limiter.limit("5 per hour")
def discover_github_repos(current_user):
    """Discover all GitHub repositories accessible with the configured token"""
    from app.api.settings import get_credential
    token = get_credential('github_token')

    if not token:
        return jsonify({'error': 'GitHub Token not configured. Set it in Settings → Credentials.'}), 400

    try:
        result = discover_all(token)
        return jsonify(result), 200
    except requests.HTTPError as e:
        # Surface the actual reason instead of a generic 502 — an expired
        # token and a rate limit need very different fixes from the user.
        status = e.response.status_code if e.response is not None else None
        message, code = _github_error_message(e.response)
        logger.error(f"GitHub discovery failed ({status}): {message}")
        return jsonify({'error': message}), code
    except requests.Timeout:
        logger.error("GitHub discovery timed out")
        return jsonify({'error': 'GitHub API timed out. Try again in a moment.'}), 504
    except requests.RequestException as e:
        # Log the exception type only — exception text can echo request details.
        logger.error("GitHub discovery connection error: %s", type(e).__name__)
        return jsonify({'error': 'Could not reach GitHub. Check the network connection.'}), 502
    except Exception as e:
        logger.error("GitHub discovery failed: %s", type(e).__name__)
        return jsonify({'error': 'GitHub API request failed'}), 502


@sources_bp.route('/<source_id>/test', methods=['POST'])
@admin_required
def test_source(current_user, source_id):
    """Test connection to a backup source"""
    sources = load_sources()
    source = next((s for s in sources if s.get('id') == source_id), None)

    if not source:
        return jsonify({'error': 'Source not found'}), 404

    source_type = source.get('type')
    source_name = source.get('name')

    # Real connection testing based on source type
    try:
        if source_type == 'local':
            # Test local directory access with path traversal protection
            import os
            path = source.get('config', {}).get('path', '')
            if not path:
                return jsonify({'error': 'Path not configured'}), 400
            # Resolve to absolute and check for traversal
            resolved = os.path.realpath(path)
            allowed_prefixes = ['/mnt/', '/data/', '/backup/', '/home/', '/opt/']
            if not any(resolved.startswith(p) for p in allowed_prefixes):
                return jsonify({'error': 'Path not in allowed directory'}), 403
            if not os.path.exists(resolved):
                return jsonify({'error': 'Path does not exist'}), 400
            if not os.access(resolved, os.R_OK):
                return jsonify({'error': 'No read permission'}), 403
            return jsonify({
                'status': 'success',
                'message': 'Local directory accessible',
                'source_id': source_id
            }), 200

        elif source_type in ('nas', 'smb'):
            # Validate authentication and read access, not only an open port.
            try:
                from app.backup.sources.smb import SMBBackup
                SMBBackup(source, backup_root_path()).test_connection()
                return jsonify({
                    'status': 'success',
                    'message': 'SMB share authentication and read access successful',
                    'source_id': source_id
                }), 200
            except Exception:
                return jsonify({
                    'error': 'SMB authentication or share access failed'
                }), 503

        elif source_type == 'portainer':
            try:
                from app.backup.sources.selfhosted import SelfHostedBackup
                stack_count = SelfHostedBackup(
                    source, backup_root_path()
                ).test_connection()
                return jsonify({
                    'status': 'success',
                    'message': f'Portainer API read access successful ({stack_count} stacks)',
                    'source_id': source_id,
                }), 200
            except Exception:
                return jsonify({'error': 'Portainer API access failed'}), 503

        elif source_type == 'github':
            # Test GitHub API access
            config = source.get('config', {})
            from app.api.settings import get_credential
            token = (
                config.get('token', '')
                or source.get('token', '')
                or get_credential(
                    'github_token', profile=config.get('credential_profile')
                )
            )
            repo = config.get('repo', '') or source.get('repo', '')
            if not token or not repo:
                return jsonify({'error': 'Token or repository not configured'}), 400

            import requests
            headers = {'Authorization': f'token {token}'}
            response = requests.get(f'https://api.github.com/repos/{repo}', headers=headers, timeout=10)

            if response.status_code == 200:
                return jsonify({
                    'status': 'success',
                    'message': f'GitHub repository {repo} accessible',
                    'source_id': source_id
                }), 200
            elif response.status_code == 401:
                return jsonify({'error': 'Invalid GitHub token'}), 400
            elif response.status_code == 404:
                return jsonify({'error': f'Repository {repo} not found'}), 404
            else:
                return jsonify({'error': f'GitHub API error: {response.status_code}'}), 503

        else:
            # Unsupported tests must never look successful to the UI.
            return jsonify({
                'status': 'unsupported',
                'message': f'Connection test for {source_type} not yet implemented. Source will be tested during actual backup.',
                'source_id': source_id
            }), 501

    except Exception as e:
        return jsonify({'error': f'Connection test failed: {str(e)}'}), 500


@sources_bp.route('/supabase/test', methods=['POST'])
@admin_required
def test_supabase_connection(current_user):
    """Test Supabase database connection. Connection String + Password come from credential profile."""
    import subprocess
    data = request.get_json() or {}

    profile = (data.get('profile') or '').strip() or None
    connection_string = (data.get('connection_string') or '').strip()

    from app.api.settings import get_credential

    if not connection_string:
        connection_string = get_credential('supabase_connection_string', profile=profile) or ''

    if not connection_string:
        return jsonify({'error': 'Connection String fehlt. Trag ihn im Credential-Profil ein oder wähle ein Profil.'}), 400

    if not connection_string.startswith('postgresql://'):
        return jsonify({'error': 'Connection String muss mit postgresql:// beginnen'}), 400

    # 1. Check if psql is available
    try:
        result = subprocess.run(
            ['psql', '--version'],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode != 0:
            return jsonify({'error': 'psql nicht verfügbar im Container'}), 500
        pg_version = result.stdout.strip()
    except FileNotFoundError:
        return jsonify({'error': 'psql nicht installiert'}), 500
    except Exception as e:
        return jsonify({'error': f'psql Check fehlgeschlagen: {str(e)}'}), 500

    # 2. Replace [YOUR-PASSWORD] placeholder with credential from profile
    db_password = get_credential('supabase_db_password', profile=profile)

    # Supabase Dashboard URL-encodes brackets: %5BYOUR-PASSWORD%5D → [YOUR-PASSWORD]
    from urllib.parse import unquote, quote
    connection_string = unquote(connection_string)

    if '[YOUR-PASSWORD]' in connection_string:
        if not db_password:
            return jsonify({
                'error': 'DB Passwort fehlt im Profil. Trag es unter Settings → Credentials ein.'
            }), 400
        connection_string = connection_string.replace('[YOUR-PASSWORD]', quote(db_password, safe=''))

    # 3. Test connection
    try:
        safe_connection, postgres_env = safe_postgres_command(connection_string)
        result = subprocess.run(
            ['psql', safe_connection, '-c', 'SELECT 1;'],
            capture_output=True,
            text=True,
            timeout=15,
            env=postgres_env,
        )

        if result.returncode == 0:
            return jsonify({
                'status': 'success',
                'message': f'Verbindung erfolgreich! ({pg_version})',
            }), 200
        else:
            error_msg = result.stderr.strip()
            if 'password authentication failed' in error_msg.lower():
                return jsonify({'error': 'DB Password falsch. Prüfe Settings → Credentials.'}), 400
            elif 'could not translate host name' in error_msg.lower():
                return jsonify({'error': 'Hostname nicht auflösbar. Prüfe den Connection String.'}), 400
            else:
                return jsonify({'error': f'Verbindung fehlgeschlagen: {error_msg}'}), 503

    except subprocess.TimeoutExpired:
        return jsonify({'error': 'Verbindung Timeout (15s) - prüfe den Connection String'}), 504
    except Exception as e:
        return jsonify({'error': f'Verbindungstest fehlgeschlagen: {str(e)}'}), 500
