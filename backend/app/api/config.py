"""
Configuration Export/Import API Endpoints
"""
from flask import Blueprint, current_app, request, jsonify, send_file
import json
import os
import tempfile

from app.api.auth import admin_required
from app.source_config import (
    load_sources,
    redact_source_secrets,
    save_sources,
    strip_redaction_markers,
)
from app.backup.paths import validate_source_id
from app.config import Config
from app.time_utils import utc_iso_z, utc_now_naive
from app.backup.artifacts import DEFAULT_BACKUP_RETENTION_COUNT
from app.runtime_settings import backup_root_path, get_setting

config_bp = Blueprint('config', __name__)


def _validate_import_sources(sources):
    """Validate source records before any imported configuration is written."""
    errors = []
    seen_ids = set()
    for index, source in enumerate(sources):
        if not isinstance(source, dict):
            errors.append(f'Source {index} is not an object')
            continue
        if not source.get('name'):
            errors.append(f'Source {index} missing name')
        if not source.get('type'):
            errors.append(f'Source {index} missing type')
        try:
            source_id = validate_source_id(source.get('id'))
        except ValueError as e:
            errors.append(f'Source {index}: {e}')
            continue
        if source_id in seen_ids:
            errors.append(f'Duplicate source ID: {source_id}')
        seen_ids.add(source_id)
    return errors


@config_bp.route('/export', methods=['GET'])
@admin_required
def export_config(current_user):
    """Export all configuration as JSON"""
    try:
        # Load sources and strip credentials
        sources = redact_source_secrets(load_sources())

        # Get system settings
        settings = {
            'backup_base_path': backup_root_path(),
            'max_parallel_tasks': int(get_setting(
                'max_parallel_tasks', Config.MAX_PARALLEL_TASKS
            )),
            'log_retention_days': int(get_setting(
                'log_retention_days', Config.LOG_RETENTION_DAYS
            )),
            'backup_retention_count': int(get_setting('backup_retention_count', DEFAULT_BACKUP_RETENTION_COUNT)),
            'auto_cleanup': str(get_setting('auto_cleanup', 'true')).lower() == 'true',
        }

        # Create export data
        export_data = {
            'version': '1.0',
            'exported_at': utc_iso_z(),
            'sources': sources,
            'settings': settings,
            'metadata': {
                'user': current_user.username,
                'total_sources': len(sources)
            }
        }

        # Create temporary file
        temp_file = tempfile.NamedTemporaryFile(
            mode='w',
            delete=False,
            suffix='.json',
            prefix='backupgenie_config_'
        )

        # Write to file
        json.dump(export_data, temp_file, indent=2)
        temp_file.close()

        # Generate filename with timestamp
        timestamp = utc_now_naive().strftime('%Y%m%d_%H%M%S')
        filename = f'backupgenie_config_{timestamp}.json'

        # Send file and schedule cleanup
        response = send_file(
            temp_file.name,
            as_attachment=True,
            download_name=filename,
            mimetype='application/json'
        )

        # Clean up temp file after response is sent
        @response.call_on_close
        def cleanup():
            try:
                os.unlink(temp_file.name)
            except OSError:
                pass

        return response

    except Exception as e:
        return jsonify({'error': 'Export failed'}), 500


@config_bp.route('/import', methods=['POST'])
@admin_required
def import_config(current_user):
    """Import configuration from JSON"""
    try:
        data = request.get_json()

        if not data:
            return jsonify({'error': 'No configuration data provided'}), 400

        # Validate schema
        if not isinstance(data, dict):
            return jsonify({'error': 'Invalid configuration format'}), 400

        if 'version' not in data:
            return jsonify({'error': 'Missing version field'}), 400

        # Validate version compatibility
        if data['version'] != '1.0':
            return jsonify({'error': f'Unsupported configuration version: {data["version"]}'}), 400

        # Get import options from query params
        merge = request.args.get('merge', 'false').lower() == 'true'

        from app import db
        from app.api.settings import (
            apply_runtime_settings,
            normalize_settings,
            stage_settings,
        )

        existing_sources = load_sources()
        final_sources = existing_sources
        imported_sources = 0
        if 'sources' in data:
            if not isinstance(data['sources'], list):
                return jsonify({'error': 'Sources must be an array'}), 400
            imported_source_data = strip_redaction_markers(data['sources'])
            source_errors = _validate_import_sources(imported_source_data)
            if source_errors:
                return jsonify({'error': 'Invalid sources', 'details': source_errors}), 400
            if merge:
                final_sources = list(existing_sources)
                existing_ids = {source.get('id') for source in final_sources}
                for source in imported_source_data:
                    if source.get('id') not in existing_ids:
                        final_sources.append(source)
                        imported_sources += 1
            else:
                final_sources = imported_source_data
                imported_sources = len(imported_source_data)

        try:
            normalized_settings = normalize_settings(data.get('settings', {}))
        except ValueError as exc:
            return jsonify({'error': str(exc)}), 400

        sources_changed = final_sources != existing_sources
        try:
            stage_settings(normalized_settings)
            if sources_changed:
                save_sources(final_sources)
            db.session.commit()
        except Exception:
            db.session.rollback()
            if sources_changed:
                try:
                    save_sources(existing_sources)
                except Exception:
                    current_app.logger.critical(
                        'Could not restore source configuration after import failure'
                    )
            raise

        apply_runtime_settings(normalized_settings)
        imported_settings = len(normalized_settings)

        return jsonify({
            'message': 'Configuration imported successfully',
            'summary': {
                'sources_imported': imported_sources,
                'settings_imported': imported_settings,
                'merge_mode': merge,
                'imported_at': utc_iso_z(),
                'imported_by': current_user.username
            }
        }), 200

    except json.JSONDecodeError:
        return jsonify({'error': 'Invalid JSON format'}), 400
    except Exception:
        current_app.logger.exception('Configuration import failed')
        return jsonify({'error': 'Import failed'}), 500


@config_bp.route('/validate', methods=['POST'])
@admin_required
def validate_config(current_user):
    """Validate configuration file without importing"""
    try:
        data = request.get_json()

        if not data:
            return jsonify({'error': 'No configuration data provided'}), 400

        errors = []
        warnings = []

        # Check version
        if 'version' not in data:
            errors.append('Missing version field')
        elif data['version'] != '1.0':
            errors.append(f'Unsupported version: {data["version"]}')

        # Validate sources
        if 'sources' in data:
            if not isinstance(data['sources'], list):
                errors.append('Sources must be an array')
            else:
                for i, source in enumerate(data['sources']):
                    if not isinstance(source, dict):
                        errors.append(f'Source {i} is not an object')
                        continue

                    # Check required fields
                    try:
                        validate_source_id(source.get('id'))
                    except ValueError as e:
                        errors.append(f'Source {i}: {e}')
                    if 'name' not in source:
                        errors.append(f'Source {i} missing name')
                    if 'type' not in source:
                        errors.append(f'Source {i} missing type')

        # Validate settings
        if 'settings' in data:
            if not isinstance(data['settings'], dict):
                errors.append('Settings must be an object')
            else:
                from app.api.settings import normalize_settings
                try:
                    normalize_settings(data['settings'])
                except ValueError as exc:
                    errors.append(str(exc))

        # Check for duplicate source IDs
        if 'sources' in data and isinstance(data['sources'], list):
            source_ids = [s.get('id') for s in data['sources'] if s.get('id')]
            if len(source_ids) != len(set(source_ids)):
                errors.append('Duplicate source IDs detected')

        is_valid = len(errors) == 0

        return jsonify({
            'valid': is_valid,
            'errors': errors,
            'warnings': warnings,
            'summary': {
                'total_sources': len(data.get('sources', [])),
                'has_settings': 'settings' in data,
                'version': data.get('version', 'unknown')
            }
        }), 200 if is_valid else 400

    except json.JSONDecodeError:
        return jsonify({
            'valid': False,
            'errors': ['Invalid JSON format'],
            'warnings': []
        }), 400
    except Exception:
        current_app.logger.exception('Configuration validation failed')
        return jsonify({
            'valid': False,
            'errors': ['Validation failed'],
            'warnings': []
        }), 500
