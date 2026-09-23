"""
Backup API Endpoints
"""
from flask import Blueprint, request, jsonify, send_file
from datetime import datetime
import os
import glob
import tarfile
import tempfile

from app import db
from app.models.backup import Backup, BackupSourceResult
from app.api.auth import admin_required, token_required
from app.backup.executor import BackupExecutor
from app.backup.jobs import (
    JobConflictError,
    JobValidationError,
    active_source_ids,
    cancel_backup_job,
    effective_parallelism,
    reserve_backup,
)
from app.backup.paths import ensure_path_within, source_backup_path
from app.backup.restore_jobs import (
    RestoreJobError,
    enqueue_restore,
    read_restore_status,
)
from app.runtime_settings import backup_root_path

backup_bp = Blueprint('backup', __name__)


def _running_source_ids():
    """Source IDs reserved by queued or running backup jobs."""
    return active_source_ids()


@backup_bp.route('/running-sources', methods=['GET'])
@token_required
def get_running_sources(current_user):
    """List source ids currently being backed up, for per-source UI state."""
    return jsonify({'source_ids': sorted(_running_source_ids())}), 200


@backup_bp.route('/start', methods=['POST'])
@admin_required
def start_backup(current_user):
    """Start a new backup"""
    data = request.get_json() or {}
    if not isinstance(data, dict):
        return jsonify({'error': 'Request body must be an object'}), 400

    from app.api.sources import load_sources

    requested_sources = data.get('sources')
    if requested_sources == []:
        requested_sources = None

    try:
        parallel = effective_parallelism(data.get('parallel'))
        backup, selected = reserve_backup(
            load_sources(),
            requested_sources,
            trigger_type='manual',
            parallel=parallel,
        )
    except JobConflictError as exc:
        return jsonify({
            'error': str(exc),
            'sources': exc.source_ids,
        }), 409
    except JobValidationError as exc:
        response = {'error': str(exc)}
        if exc.source_ids:
            response['sources'] = exc.source_ids
        return jsonify(response), exc.status_code

    return jsonify({
        'backup_id': backup.backup_id,
        'status': 'queued',
        'started_at': backup.started_at.isoformat(),
        'sources': len(selected),
        'parallel': parallel,
    }), 202


@backup_bp.route('/<backup_id>', methods=['GET'])
@token_required
def get_backup_status(current_user, backup_id):
    """Get backup status"""
    backup = Backup.query.filter_by(backup_id=backup_id).first()

    if not backup:
        return jsonify({'error': 'Backup not found'}), 404

    return jsonify(backup.to_dict()), 200


@backup_bp.route('/history', methods=['GET'])
@token_required
def get_backup_history(current_user):
    """Get backup history"""
    limit = request.args.get('limit', 20, type=int)
    offset = request.args.get('offset', 0, type=int)

    total = Backup.query.count()
    backups = Backup.query.order_by(Backup.started_at.desc()).limit(limit).offset(offset).all()

    return jsonify({
        'total': total,
        'limit': limit,
        'offset': offset,
        'backups': [backup.to_dict() for backup in backups]
    }), 200


@backup_bp.route('/<backup_id>/stop', methods=['POST'])
@admin_required
def stop_backup(current_user, backup_id):
    """Stop a running backup gracefully"""
    backup = Backup.query.filter_by(backup_id=backup_id).first()

    if not backup:
        return jsonify({'error': 'Backup not found'}), 404

    backup, state = cancel_backup_job(backup_id)
    if state == 'not_found':
        return jsonify({'error': 'Backup not found'}), 404
    if state == 'not_running':
        return jsonify({'error': 'Backup is not running'}), 400
    if state == 'cancelling':
        BackupExecutor.stop_backup(backup_id)
        return jsonify({
            'message': 'Backup stop requested (will complete current source)',
            'backup_id': backup_id,
            'status': 'cancelling',
        }), 200

    return jsonify({
        'message': 'Queued backup cancelled',
        'backup_id': backup_id,
        'status': 'cancelled',
    }), 200


@backup_bp.route('/stats', methods=['GET'])
@token_required
def get_stats(current_user):
    """Get backup statistics"""
    total_backups = Backup.query.count()
    successful = Backup.query.filter_by(status='completed').count()
    failed = Backup.query.filter_by(status='failed').count()
    running = Backup.query.filter(
        Backup.status.in_(('pending', 'running', 'cancelling'))
    ).count()

    # Last backup
    last_backup = Backup.query.order_by(Backup.started_at.desc()).first()

    # Total size
    total_size = db.session.query(db.func.sum(Backup.total_size)).scalar() or 0

    return jsonify({
        'total_backups': total_backups,
        'successful': successful,
        'failed': failed,
        'running': running,
        'total_size_bytes': total_size,
        'last_backup': last_backup.to_dict() if last_backup else None
    }), 200


@backup_bp.route('/all', methods=['DELETE'])
@admin_required
def delete_all_backups(current_user):
    """Delete all backup records (DANGEROUS - requires confirmation)"""
    # Require explicit confirmation parameter
    confirm = request.args.get('confirm', '').lower() == 'true'

    if not confirm:
        return jsonify({
            'error': 'Confirmation required',
            'message': 'Add ?confirm=true to delete all backups'
        }), 400

    try:
        # Delete all backup source results first (foreign key constraint)
        source_results_count = BackupSourceResult.query.delete()

        # Delete all backups
        backups_count = Backup.query.delete()

        db.session.commit()

        return jsonify({
            'message': f'Deleted {backups_count} backups and {source_results_count} source results',
            'backups_deleted': backups_count,
            'source_results_deleted': source_results_count
        }), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Failed to delete backups: {str(e)}'}), 500


@backup_bp.route('/download/<source_id>', methods=['GET'])
@admin_required
def list_downloadable(current_user, source_id):
    """List downloadable backup files for a source"""
    try:
        backup_dir = source_backup_path(backup_root_path(), source_id)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400

    if not os.path.exists(backup_dir):
        return jsonify({'files': []}), 200

    files = []

    # Existing tar.gz archives
    for archive in sorted(glob.glob(os.path.join(backup_dir, '*.tar.gz')), reverse=True):
        stat = os.stat(archive)
        files.append({
            'filename': os.path.basename(archive),
            'size': stat.st_size,
            'modified': datetime.utcfromtimestamp(stat.st_mtime).isoformat(),
            'type': 'archive',
        })

    # Bare git mirrors (.git dirs) — one entry per repo
    for git_dir in sorted(glob.glob(os.path.join(backup_dir, '*.git')), reverse=True):
        if os.path.isdir(git_dir):
            total = sum(
                os.path.getsize(os.path.join(dp, f))
                for dp, _, fs in os.walk(git_dir) for f in fs
            )
            stat = os.stat(git_dir)
            files.append({
                'filename': os.path.basename(git_dir),
                'size': total,
                'modified': datetime.utcfromtimestamp(stat.st_mtime).isoformat(),
                'type': 'directory',
            })

    # Generic directories (supabase dumps etc.)
    from app.backup.artifacts import WORKING_DIR_NAMES
    for d in sorted(glob.glob(os.path.join(backup_dir, '*')), reverse=True):
        if os.path.basename(d) in WORKING_DIR_NAMES:
            continue
        if os.path.isdir(d) and not d.endswith('.git') and not d.endswith('_restore_tmp'):
            total = sum(
                os.path.getsize(os.path.join(dp, f))
                for dp, _, fs in os.walk(d) for f in fs
            )
            stat = os.stat(d)
            files.append({
                'filename': os.path.basename(d),
                'size': total,
                'modified': datetime.utcfromtimestamp(stat.st_mtime).isoformat(),
                'type': 'directory',
            })

    return jsonify({'source_id': source_id, 'files': files}), 200


@backup_bp.route('/download/<source_id>/<path:filename>', methods=['GET'])
@admin_required
def download_backup_file(current_user, source_id, filename):
    """Download a single backup file or pack a directory as tar.gz on the fly"""
    import re

    # Prevent path traversal
    if '..' in filename or filename.startswith('/'):
        return jsonify({'error': 'Invalid filename'}), 400

    try:
        backup_dir = source_backup_path(backup_root_path(), source_id)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    target = os.path.join(backup_dir, filename)

    # Resolve and verify still inside backup_dir
    try:
        real_target = ensure_path_within(backup_dir, target)
    except ValueError:
        return jsonify({'error': 'Access denied'}), 403

    if not os.path.exists(real_target):
        return jsonify({'error': 'File not found'}), 404

    if os.path.isfile(real_target):
        return send_file(real_target, as_attachment=True, download_name=filename)

    # Directory: pack into tar.gz in a temp file and stream it
    if os.path.isdir(real_target):
        archive_name = filename.rstrip('/') + '.tar.gz'
        tmp = tempfile.NamedTemporaryFile(suffix='.tar.gz', delete=False)
        tmp.close()
        try:
            with tarfile.open(tmp.name, 'w:gz') as tar:
                tar.add(real_target, arcname=os.path.basename(real_target))
            response = send_file(tmp.name, as_attachment=True, download_name=archive_name)

            @response.call_on_close
            def cleanup_tmp_archive():
                try:
                    os.unlink(tmp.name)
                except OSError:
                    pass

            return response
        except Exception as e:
            os.unlink(tmp.name)
            return jsonify({'error': str(e)}), 500

    return jsonify({'error': 'Unsupported file type'}), 400


@backup_bp.route('/restore/available/<source_id>', methods=['GET'])
@admin_required
def get_available_restores(current_user, source_id):
    """List available backups for restore for a given source"""
    import os
    import glob

    try:
        backup_dir = source_backup_path(backup_root_path(), source_id)
    except ValueError as e:
        return jsonify({'error': str(e), 'backups': []}), 400

    if not os.path.exists(backup_dir):
        return jsonify({'error': 'Kein Backup-Verzeichnis gefunden', 'backups': []}), 200

    available = []

    # Find tar.gz archives
    for archive in sorted(glob.glob(os.path.join(backup_dir, '*.tar.gz')), reverse=True):
        name = os.path.basename(archive)
        stat = os.stat(archive)
        available.append({
            'path': archive,
            'filename': name,
            'size': stat.st_size,
            'created': datetime.fromtimestamp(stat.st_mtime).isoformat(),
            'type': 'archive'
        })

    # Find uncompressed backup directories
    for d in sorted(glob.glob(os.path.join(backup_dir, 'supabase_*')), reverse=True):
        if os.path.isdir(d) and not d.endswith('_restore_tmp'):
            name = os.path.basename(d)
            stat = os.stat(d)
            # Calculate directory size
            dir_size = sum(
                os.path.getsize(os.path.join(dirpath, f))
                for dirpath, _, filenames in os.walk(d)
                for f in filenames
            )
            available.append({
                'path': d,
                'filename': name,
                'size': dir_size,
                'created': datetime.fromtimestamp(stat.st_mtime).isoformat(),
                'type': 'directory'
            })

    return jsonify({
        'source_id': source_id,
        'backups': available
    }), 200


@backup_bp.route('/restore', methods=['POST'])
@admin_required
def start_restore(current_user):
    """Queue a durable Supabase restore operation."""
    data = request.get_json() or {}
    if not isinstance(data, dict):
        return jsonify({'error': 'Request body must be an object'}), 400

    backup_path = data.get('backup_path', '')
    profile = (data.get('profile') or '').strip() or None
    target_connection_string = data.get('target_connection_string', '')
    target_db_password = data.get('target_db_password', '')
    restore_storage = data.get('restore_storage', False)
    target_service_role_key = data.get('target_service_role_key', '')

    if not backup_path:
        return jsonify({'error': 'backup_path ist erforderlich'}), 400

    # Fetch missing values from credential profile (if provided)
    from app.api.settings import get_credential
    if not target_connection_string:
        target_connection_string = get_credential('supabase_connection_string', profile=profile) or ''
    if not target_connection_string:
        return jsonify({'error': 'Connection String fehlt. Wähle ein Profil oder trag den Connection String ein.'}), 400

    if not target_db_password and '[YOUR-PASSWORD]' in target_connection_string:
        target_db_password = get_credential('supabase_db_password', profile=profile)
        if not target_db_password:
            return jsonify({'error': 'Kein DB Passwort im Profil. Trag es in den Credentials ein.'}), 400

    import os

    try:
        real_backup_path = ensure_path_within(backup_root_path(), backup_path)
    except ValueError:
        return jsonify({'error': 'Backup-Pfad außerhalb des Backup-Verzeichnisses'}), 403

    if not os.path.exists(real_backup_path):
        return jsonify({'error': f'Backup nicht gefunden: {backup_path}'}), 404

    job = enqueue_restore({
        'backup_path': real_backup_path,
        'target_config': {
            'profile': profile,
            'target_connection_string': target_connection_string,
            'target_db_password': target_db_password,
            'restore_storage': bool(restore_storage),
            'target_service_role_key': target_service_role_key,
        },
    })

    return jsonify({
        'restore_id': job['restore_id'],
        'status': job['status'],
        'message': 'Restore eingereiht'
    }), 202


@backup_bp.route('/restore/<restore_id>', methods=['GET'])
@token_required
def get_restore_status(current_user, restore_id):
    """Get durable restore operation status."""
    try:
        status = read_restore_status(restore_id)
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    except RestoreJobError:
        return jsonify({'error': 'Restore-Status ist beschädigt'}), 500
    if not status:
        return jsonify({'error': 'Restore nicht gefunden'}), 404
    return jsonify(status), 200
