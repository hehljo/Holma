#!/usr/bin/env python3
"""
Gate: every backup run becomes exactly one rotatable artifact.

Exercises RunArtifact and select_expired on real files: the archive, folder
and snapshot modes, failed and empty runs, hard-link sharing between
snapshots, and the restore path for a run archive that wraps a Supabase
archive. Also pins the artifact mode of the large file-tree handlers, because
an accidental 'archive' there gzips a whole NAS share on every run.
"""
import os
import shutil
import sys
import tarfile
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.backup.artifacts import (  # noqa: E402
    CURRENT_DIRNAME, MODE_ARCHIVE, MODE_FOLDER, MODE_SNAPSHOT, MODES,
    RunArtifact, select_expired,
)
from app.backup.sources.git_archive import MIRROR_DIRNAME  # noqa: E402

TS1, TS2, TS3 = '20260901_100000', '20260902_100000', '20260903_100000'


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write(text)


class RunArtifactTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='holma_artifact_')
        self.source_dir = os.path.join(self.tmp, 'src1')

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def listing(self):
        return sorted(os.listdir(self.source_dir))

    # -- archive -----------------------------------------------------------

    def test_archive_run_becomes_one_tar_gz(self):
        os.makedirs(os.path.join(self.source_dir, MIRROR_DIRNAME, 'repo.git'))
        artifact = RunArtifact(self.source_dir, 'src1', TS1, MODE_ARCHIVE)
        target = artifact.prepare()
        write(os.path.join(target, 'repo_a.tar.gz'), 'a')
        write(os.path.join(target, 'repo_b.tar.gz'), 'b')

        artifact.finalize('completed')

        self.assertEqual(self.listing(), [MIRROR_DIRNAME, f'src1_{TS1}.tar.gz'])
        with tarfile.open(os.path.join(self.source_dir, f'src1_{TS1}.tar.gz')) as tar:
            names = sorted(tar.getnames())
        self.assertIn(f'src1_{TS1}/repo_a.tar.gz', names)
        self.assertIn(f'src1_{TS1}/repo_b.tar.gz', names)

    def test_partial_run_is_kept(self):
        artifact = RunArtifact(self.source_dir, 'src1', TS1, MODE_ARCHIVE)
        write(os.path.join(artifact.prepare(), 'dump.sql'), 'x')
        artifact.finalize('partial')
        self.assertEqual(self.listing(), [f'src1_{TS1}.tar.gz'])

    def test_failed_run_leaves_no_version(self):
        artifact = RunArtifact(self.source_dir, 'src1', TS1, MODE_ARCHIVE)
        write(os.path.join(artifact.prepare(), 'half.sql'), 'x')
        artifact.finalize('failed')
        self.assertEqual(self.listing(), [])

    def test_empty_run_leaves_no_version(self):
        artifact = RunArtifact(self.source_dir, 'src1', TS1, MODE_ARCHIVE)
        artifact.prepare()
        artifact.finalize('completed')
        self.assertEqual(self.listing(), [])

    def test_stale_staging_is_cleared(self):
        write(os.path.join(self.source_dir, f'.run_{TS1}', 'old.sql'), 'x')
        write(os.path.join(self.source_dir, f'.src1_{TS1}.partial.tar.gz'), 'x')
        RunArtifact(self.source_dir, 'src1', TS2, MODE_ARCHIVE).prepare()
        self.assertEqual(self.listing(), [f'.run_{TS2}'])

    # -- folder ------------------------------------------------------------

    def test_folder_run_is_renamed_not_packed(self):
        artifact = RunArtifact(self.source_dir, 'src1', TS1, MODE_FOLDER)
        write(os.path.join(artifact.prepare(), 'vzdump.vma.zst'), 'vm')
        artifact.finalize('completed')
        self.assertEqual(self.listing(), [f'src1_{TS1}'])
        self.assertTrue(os.path.isfile(
            os.path.join(self.source_dir, f'src1_{TS1}', 'vzdump.vma.zst')))

    # -- snapshot ----------------------------------------------------------

    @unittest.skipUnless(shutil.which('rsync'), 'rsync not installed')
    def test_snapshots_share_unchanged_files(self):
        def run(ts, mutate):
            artifact = RunArtifact(self.source_dir, 'nas', ts, MODE_SNAPSHOT)
            current = artifact.prepare()
            mutate(current)
            artifact.finalize('completed')
            return os.path.join(self.source_dir, f'nas_{ts}')

        def first(current):
            write(os.path.join(current, 'same.txt'), 'unchanged')
            write(os.path.join(current, 'changes.txt'), 'v1')
            write(os.path.join(current, 'gone.txt'), 'deleted later')

        def second(current):
            # Sync tools carry the source mtime; rsync's quick check (size +
            # mtime) is what decides between hard link and copy.
            write(os.path.join(current, 'changes.txt'), 'v2')
            os.utime(os.path.join(current, 'changes.txt'), (2_000_000_000, 2_000_000_000))
            os.unlink(os.path.join(current, 'gone.txt'))

        snap1 = run(TS1, first)
        snap2 = run(TS2, second)

        self.assertEqual(self.listing(), [CURRENT_DIRNAME, f'nas_{TS1}', f'nas_{TS2}'])
        same1 = os.stat(os.path.join(snap1, 'same.txt'))
        same2 = os.stat(os.path.join(snap2, 'same.txt'))
        self.assertEqual(same1.st_ino, same2.st_ino, 'unchanged file must be a hard link')
        with open(os.path.join(snap1, 'changes.txt')) as fh:
            self.assertEqual(fh.read(), 'v1')
        with open(os.path.join(snap2, 'changes.txt')) as fh:
            self.assertEqual(fh.read(), 'v2')
        self.assertTrue(os.path.exists(os.path.join(snap1, 'gone.txt')))
        self.assertFalse(os.path.exists(os.path.join(snap2, 'gone.txt')))

        # A sync tool writing in place into _current must not reach a snapshot.
        with open(os.path.join(self.source_dir, CURRENT_DIRNAME, 'same.txt'), 'w') as fh:
            fh.write('overwritten in place')
        with open(os.path.join(snap2, 'same.txt')) as fh:
            self.assertEqual(fh.read(), 'unchanged')

    @unittest.skipUnless(shutil.which('rsync'), 'rsync not installed')
    def test_failed_snapshot_run_keeps_working_copy_only(self):
        artifact = RunArtifact(self.source_dir, 'nas', TS1, MODE_SNAPSHOT)
        write(os.path.join(artifact.prepare(), 'file.txt'), 'x')
        artifact.finalize('failed')
        self.assertEqual(self.listing(), [CURRENT_DIRNAME])

    # -- retention ---------------------------------------------------------

    def test_retention_keeps_newest_versions(self):
        names = [MIRROR_DIRNAME, CURRENT_DIRNAME, f'.run_{TS1}',
                 f'.src1_{TS1}.partial.tar.gz', 'x_restore_tmp']
        names += [f'src1_2026090{d}_100000.tar.gz' for d in range(1, 6)]
        expired = select_expired(names, 3)
        self.assertEqual(sorted(expired), [
            'src1_20260901_100000.tar.gz', 'src1_20260902_100000.tar.gz',
        ])

    def test_retention_under_limit_deletes_nothing(self):
        names = [MIRROR_DIRNAME, f'src1_{TS1}.tar.gz', f'src1_{TS2}']
        self.assertEqual(select_expired(names, 3), [])

    def test_legacy_loose_files_rotate_by_their_stamp(self):
        names = [f'repo_{TS1}.tar.gz', f'other_{TS1}.tar.gz',
                 f'src1_{TS2}.tar.gz', f'src1_{TS3}.tar.gz']
        self.assertEqual(sorted(select_expired(names, 2)),
                         [f'other_{TS1}.tar.gz', f'repo_{TS1}.tar.gz'])


class RestoreUnwrapTests(unittest.TestCase):
    """A Supabase run archive wraps the handler's own archive."""

    def test_nested_supabase_archive_is_found(self):
        from app.backup.restore import SupabaseRestore

        tmp = tempfile.mkdtemp(prefix='holma_restore_')
        try:
            inner_src = os.path.join(tmp, 'build', 'supabase_20260901_100000')
            write(os.path.join(inner_src, 'schema_20260901_100000.sql'), '-- schema')
            staging = os.path.join(tmp, 'staging')
            os.makedirs(staging)
            with tarfile.open(os.path.join(staging, 'supabase_ref_20260901_100000.tar.gz'),
                              'w:gz') as tar:
                tar.add(inner_src, arcname='supabase_20260901_100000')

            extract_dir = os.path.join(tmp, 'extract')
            os.makedirs(extract_dir)
            working = SupabaseRestore()._unwrap_nested_archive(staging, extract_dir)
            self.assertTrue(os.path.isfile(
                os.path.join(working, 'schema_20260901_100000.sql')))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class HandlerModeTests(unittest.TestCase):
    """Large file-tree sources must never be gzipped as a whole per run."""

    def mode(self, module, cls, config):
        mod = __import__(f'app.backup.sources.{module}', fromlist=[cls])
        return getattr(mod, cls)(config, '/nonexistent').artifact_mode()

    def test_large_sources_are_not_archived(self):
        cases = [
            ('local', 'LocalBackup', {'type': 'local'}),
            ('rclone', 'RcloneBackup', {'type': 'rclone'}),
            ('rsync_ssh', 'RsyncSSHBackup', {'type': 'rsync-ssh'}),
            ('ftp', 'FTPBackup', {'type': 'ftp'}),
            ('ftp', 'SFTPBackup', {'type': 'sftp'}),
            ('webdav', 'WebDAVBackup', {'type': 'webdav'}),
            ('smb', 'SMBBackup', {'type': 'smb'}),
            ('smb', 'SMBBackup', {'type': 'nfs'}),
            ('proxmox', 'ProxmoxBackup', {'type': 'proxmox'}),
            ('selfhosted', 'SelfHostedBackup', {'type': 'nextcloud', 'backup_method': 'rsync'}),
        ]
        for module, cls, config in cases:
            with self.subTest(handler=cls, type=config['type']):
                mode = self.mode(module, cls, config)
                self.assertIn(mode, MODES)
                self.assertNotEqual(mode, MODE_ARCHIVE)

    def test_small_sources_are_archived(self):
        cases = [
            ('github', 'GitHubBackup', {'type': 'github'}),
            ('supabase', 'SupabaseBackup', {'type': 'supabase'}),
            ('database', 'PostgreSQLBackup', {'type': 'postgresql'}),
            ('selfhosted', 'SelfHostedBackup', {'type': 'vaultwarden'}),
        ]
        for module, cls, config in cases:
            with self.subTest(handler=cls):
                self.assertEqual(self.mode(module, cls, config), MODE_ARCHIVE)


class ExecutorWiringTests(unittest.TestCase):
    """The executor must route every run through RunArtifact."""

    def setUp(self):
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            'app', 'backup', 'executor.py')
        with open(path, encoding='utf-8') as fh:
            self.src = fh.read()

    def test_handler_writes_into_prepared_target(self):
        self.assertIn('handler.dest_path = artifact.prepare()', self.src)

    def test_status_decides_about_the_artifact(self):
        self.assertIn("artifact.finalize(backup_result['status'])", self.src)

    def test_raising_handler_discards_staging(self):
        start = self.src.find('backup_result = normalize_backup_result(handler.backup())')
        self.assertGreater(start, 0)
        self.assertIn('artifact.discard()', self.src[start:start + 200])


if __name__ == '__main__':
    result = unittest.main(exit=False, verbosity=1).result
    if result.testsRun == 0:
        sys.exit(2)
    sys.exit(0 if result.wasSuccessful() else 1)
