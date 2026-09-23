"""Filesystem path guards shared by backup, download, and restore flows."""

import os
import re


_SOURCE_ID_PATTERN = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$')


def validate_source_id(source_id):
    """Return a safe source id or raise ``ValueError``.

    Source ids become directory names and database values. Keep the accepted
    alphabet deliberately small so the same id is safe on every supported
    host filesystem.
    """
    if not isinstance(source_id, str) or not _SOURCE_ID_PATTERN.fullmatch(source_id):
        raise ValueError(
            'Source ID must be 1-100 characters using letters, numbers, dot, '
            'underscore, or hyphen, and must start with a letter or number'
        )
    return source_id


def ensure_path_within(base_path, candidate_path, *, allow_base=False):
    """Resolve ``candidate_path`` and ensure it stays below ``base_path``."""
    real_base = os.path.realpath(base_path)
    real_candidate = os.path.realpath(candidate_path)
    try:
        inside = os.path.commonpath((real_base, real_candidate)) == real_base
    except ValueError:
        inside = False

    if not inside or (not allow_base and real_candidate == real_base):
        raise ValueError('Path is outside the allowed directory')
    return real_candidate


def source_backup_path(backup_base_path, source_id):
    """Return the guarded backup directory for one source."""
    safe_id = validate_source_id(source_id)
    return ensure_path_within(
        backup_base_path,
        os.path.join(backup_base_path, safe_id),
    )

