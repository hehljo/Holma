#!/usr/bin/env python3
"""Regression checks for source-path and restore safety guards."""

import io
import os
import sys
import tarfile
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch


BACKEND_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

from app.backup.paths import ensure_path_within, source_backup_path, validate_source_id
from app.backup.restore import SupabaseRestore, _safe_extract
from app.api.config import _validate_import_sources


class SourcePathTests(unittest.TestCase):
    def test_accepts_expected_source_ids(self):
        for source_id in ('nas-test', 'github_repo.1', 'A', '123-source'):
            self.assertEqual(validate_source_id(source_id), source_id)

    def test_rejects_path_and_type_confusion(self):
        for source_id in ('..', '.', '../nas', '/tmp/nas', 'nas/test', 'nas test', '', None, 123):
            with self.subTest(source_id=source_id):
                with self.assertRaises(ValueError):
                    validate_source_id(source_id)

    def test_source_path_stays_below_backup_root(self):
        with tempfile.TemporaryDirectory() as root:
            expected = os.path.join(os.path.realpath(root), 'nas-test')
            self.assertEqual(source_backup_path(root, 'nas-test'), expected)
            with self.assertRaises(ValueError):
                ensure_path_within(root, root)

    def test_config_import_rejects_unsafe_and_duplicate_ids(self):
        errors = _validate_import_sources([
            {'id': '..', 'name': 'Unsafe', 'type': 'local'},
            {'id': 'nas-test', 'name': 'NAS 1', 'type': 'smb'},
            {'id': 'nas-test', 'name': 'NAS 2', 'type': 'smb'},
        ])
        self.assertTrue(any('Source 0' in error for error in errors))
        self.assertTrue(any('Duplicate source ID' in error for error in errors))


class TarExtractionTests(unittest.TestCase):
    def _archive(self, members):
        stream = io.BytesIO()
        with tarfile.open(fileobj=stream, mode='w:gz') as archive:
            for member, content in members:
                archive.addfile(member, io.BytesIO(content) if content is not None else None)
        stream.seek(0)
        return stream

    def test_extracts_regular_file(self):
        member = tarfile.TarInfo('backup/schema.sql')
        payload = b'SELECT 1;'
        member.size = len(payload)
        with tempfile.TemporaryDirectory() as destination:
            with tarfile.open(fileobj=self._archive([(member, payload)]), mode='r:gz') as archive:
                _safe_extract(archive, destination)
            self.assertTrue(os.path.isfile(os.path.join(destination, 'backup', 'schema.sql')))

    def test_rejects_parent_traversal(self):
        member = tarfile.TarInfo('../outside.sql')
        payload = b'bad'
        member.size = len(payload)
        with tempfile.TemporaryDirectory() as destination:
            with tarfile.open(fileobj=self._archive([(member, payload)]), mode='r:gz') as archive:
                with self.assertRaises(ValueError):
                    _safe_extract(archive, destination)

    def test_rejects_symlink_and_hardlink(self):
        for member_type in (tarfile.SYMTYPE, tarfile.LNKTYPE):
            member = tarfile.TarInfo('backup/link')
            member.type = member_type
            member.linkname = '../../outside'
            with self.subTest(member_type=member_type):
                with tempfile.TemporaryDirectory() as destination:
                    with tarfile.open(fileobj=self._archive([(member, None)]), mode='r:gz') as archive:
                        with self.assertRaises(ValueError):
                            _safe_extract(archive, destination)


class PsqlRestoreTests(unittest.TestCase):
    def test_psql_uses_stop_on_error(self):
        completed = SimpleNamespace(returncode=0, stdout='ok', stderr='')
        with patch('app.backup.restore.subprocess.run', return_value=completed) as run:
            result = SupabaseRestore()._run_psql('postgresql://example/db', '/tmp/schema.sql')
        self.assertTrue(result['success'])
        self.assertIn('ON_ERROR_STOP=on', run.call_args.args[0])

    def test_stderr_error_never_reports_success(self):
        completed = SimpleNamespace(
            returncode=0,
            stdout='',
            stderr='psql:/tmp/schema.sql:1: ERROR: relation failed',
        )
        with patch('app.backup.restore.subprocess.run', return_value=completed):
            result = SupabaseRestore()._run_psql('postgresql://example/db', '/tmp/schema.sql')
        self.assertFalse(result['success'])
        self.assertIn('ERROR:', result['error'])

    def test_empty_backup_is_rejected(self):
        with tempfile.TemporaryDirectory() as backup_dir:
            with patch('app.api.settings.get_credential', return_value=''):
                with self.assertRaisesRegex(ValueError, 'keine wiederherstellbaren'):
                    SupabaseRestore().restore(
                        backup_dir,
                        {'target_connection_string': 'postgresql://db.example/project'},
                    )

    def test_failed_schema_is_partial_and_not_completed(self):
        with tempfile.TemporaryDirectory() as backup_dir:
            schema_file = os.path.join(backup_dir, 'schema_20260901.sql')
            with open(schema_file, 'w', encoding='utf-8') as file:
                file.write('SELECT broken;')

            restorer = SupabaseRestore()
            with patch.object(
                restorer,
                '_run_psql',
                return_value={'success': False, 'error': 'schema failed'},
            ), patch('app.api.settings.get_credential', return_value=''):
                    result = restorer.restore(
                        backup_dir,
                        {'target_connection_string': 'postgresql://db.example/project'},
                    )

        self.assertEqual(result['status'], 'partial')
        self.assertEqual(result['steps_total'], 1)
        self.assertEqual(result['steps_completed'], 0)


if __name__ == '__main__':
    unittest.main(verbosity=2)
