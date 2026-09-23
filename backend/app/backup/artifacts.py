"""
One timestamped artifact per source and run.

Retention rotates what carries a run timestamp. Handlers used to write loose
files, bare mirrors or plain sync folders straight into the source directory,
so many sources had nothing retention could match, and the ones that did left
dozens of loose files per run. The executor now wraps every run into exactly
one artifact, chosen by the handler's artifact mode:

``archive``  (default, small sources: Git, databases, Supabase, Docker, APIs)
    The handler writes into a hidden staging directory. The executor packs it
    into ``<source>_<timestamp>.tar.gz``. Per-repository archives of the Git
    handlers end up inside it - one archive per repository, one per run.

``folder``   (large, already packed output: Proxmox dumps, SMB tar streams)
    Like ``archive``, but the staging directory is only renamed to
    ``<source>_<timestamp>/``. Gzipping a 50 GB VM dump again costs hours of
    CPU on a Pi and saves nothing.

``snapshot`` (large file trees: NAS, rsync, rclone, FTP, WebDAV, local)
    The handler keeps syncing incrementally into ``_current``. The executor
    then copies it to ``<source>_<timestamp>/`` with ``rsync --link-dest``
    against the previous snapshot, so unchanged files are hard links and a
    100 GB share with three versions costs 100 GB plus the changes, not 300 GB.
    ``_current`` itself is never hard-linked, so an in-place write by the sync
    tool cannot alter an existing snapshot.

A failed run produces no artifact. Otherwise a broken run would count as a
version and rotate a good one out.

No Flask imports here: tests call these functions directly.
"""
import os
import re
import shutil
import subprocess
import tarfile

from app.backup.sources.git_archive import MIRROR_DIRNAME

CURRENT_DIRNAME = '_current'
STAGING_PREFIX = '.run_'
TIMESTAMP_FORMAT = '%Y%m%d_%H%M%S'

# Directory names inside a source folder that hold incremental working state
# rather than backup versions. Retention and download listings skip them.
WORKING_DIR_NAMES = frozenset({MIRROR_DIRNAME, CURRENT_DIRNAME})

DEFAULT_BACKUP_RETENTION_COUNT = 3

MODE_ARCHIVE = 'archive'
MODE_FOLDER = 'folder'
MODE_SNAPSHOT = 'snapshot'
MODES = (MODE_ARCHIVE, MODE_FOLDER, MODE_SNAPSHOT)

SNAPSHOT_TIMEOUT_SECONDS = 24 * 3600


def artifact_basename(source_id, timestamp):
    return f'{source_id}_{timestamp}'


def artifact_filename(source_id, timestamp, mode):
    base = artifact_basename(source_id, timestamp)
    return f'{base}.tar.gz' if mode == MODE_ARCHIVE else base


def _remove(path):
    if os.path.isdir(path) and not os.path.islink(path):
        shutil.rmtree(path, ignore_errors=True)
    elif os.path.lexists(path):
        try:
            os.unlink(path)
        except OSError:
            pass


class RunArtifact:
    """Staging and finalizing of one source's output for one run."""

    def __init__(self, source_dir, source_id, timestamp, mode):
        if mode not in MODES:
            raise ValueError(f'Unknown artifact mode: {mode}')
        self.source_dir = source_dir
        self.source_id = source_id
        self.timestamp = timestamp
        self.mode = mode
        self.basename = artifact_basename(source_id, timestamp)
        self.final_path = os.path.join(
            source_dir, artifact_filename(source_id, timestamp, mode)
        )
        self.staging_path = os.path.join(source_dir, f'{STAGING_PREFIX}{timestamp}')
        self.current_path = os.path.join(source_dir, CURRENT_DIRNAME)

    # -- lifecycle ---------------------------------------------------------

    def prepare(self):
        """Create the handler's write target and return it.

        Leftovers of an interrupted run (staging dirs, partial artifacts) are
        removed first. Only one run per source can be active, so anything
        hidden with these prefixes is stale.
        """
        os.makedirs(self.source_dir, exist_ok=True)
        for name in os.listdir(self.source_dir):
            if name.startswith(STAGING_PREFIX) or (
                name.startswith('.') and '.partial' in name
            ):
                _remove(os.path.join(self.source_dir, name))

        if self.mode == MODE_SNAPSHOT:
            os.makedirs(self.current_path, exist_ok=True)
            return self.current_path
        os.makedirs(self.staging_path)
        return self.staging_path

    def finalize(self, status):
        """Turn the run's output into one artifact. Returns a log line."""
        if status == 'failed':
            self.discard()
            return 'Kein Backup-Artefakt: Lauf fehlgeschlagen, vorhandene Versionen bleiben.'

        if self.mode == MODE_SNAPSHOT:
            self._write_snapshot()
        else:
            if not os.listdir(self.staging_path):
                self.discard()
                return 'Kein Backup-Artefakt: der Lauf hat keine Daten geliefert.'
            if self.mode == MODE_ARCHIVE:
                self._write_archive()
            else:
                os.replace(self.staging_path, self.final_path)

        size = artifact_size(self.final_path)
        return f'Backup-Artefakt: {os.path.basename(self.final_path)} ({size} bytes)'

    def discard(self):
        """Drop this run's staged output. The working copy stays."""
        if self.mode != MODE_SNAPSHOT:
            _remove(self.staging_path)

    # -- writers -----------------------------------------------------------

    def _partial_path(self, suffix=''):
        return os.path.join(self.source_dir, f'.{self.basename}.partial{suffix}')

    def _write_archive(self):
        tmp_path = self._partial_path('.tar.gz')
        try:
            with tarfile.open(tmp_path, 'w:gz') as tar:
                tar.add(self.staging_path, arcname=self.basename)
            os.replace(tmp_path, self.final_path)
        except BaseException:
            _remove(tmp_path)
            raise
        _remove(self.staging_path)

    def _write_snapshot(self):
        tmp_path = self._partial_path()
        cmd = ['rsync', '-a', '--delete']
        previous = self.previous_snapshot()
        if previous:
            cmd.append(f'--link-dest={previous}')
        cmd.extend([self.current_path + os.sep, tmp_path + os.sep])
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=SNAPSHOT_TIMEOUT_SECONDS
            )
            if result.returncode != 0:
                raise RuntimeError(
                    f'Snapshot fehlgeschlagen (rsync {result.returncode}): '
                    f'{result.stderr.strip()[:500]}'
                )
            os.replace(tmp_path, self.final_path)
        except BaseException:
            _remove(tmp_path)
            raise

    def previous_snapshot(self):
        """Absolute path of the newest earlier snapshot of this source."""
        pattern = re.compile(rf'^{re.escape(self.source_id)}_\d{{8}}_\d{{6}}$')
        candidates = sorted(
            name for name in os.listdir(self.source_dir)
            if pattern.fullmatch(name)
            and os.path.isdir(os.path.join(self.source_dir, name))
            and name != self.basename
        )
        if not candidates:
            return None
        return os.path.realpath(os.path.join(self.source_dir, candidates[-1]))


_VERSION_STAMP = re.compile(r'(\d{8}_\d{6})')


def select_expired(names, keep_count):
    """Names in a source directory that retention should delete.

    Entries are grouped by the run timestamp in their name; the newest
    ``keep_count`` groups stay. Working directories, hidden entries (staging,
    partial artifacts) and restore temp dirs are never versions.
    """
    if keep_count < 1:
        return []
    versions = {}
    for name in names:
        if name in WORKING_DIR_NAMES or name.startswith('.') or name.endswith('_restore_tmp'):
            continue
        match = _VERSION_STAMP.search(name)
        if match:
            versions.setdefault(match.group(1), []).append(name)
    expired_stamps = sorted(versions, reverse=True)[keep_count:]
    return [name for stamp in expired_stamps for name in versions[stamp]]


def artifact_size(path):
    if os.path.isfile(path):
        return os.path.getsize(path)
    total = 0
    for dirpath, _, filenames in os.walk(path):
        for name in filenames:
            try:
                total += os.lstat(os.path.join(dirpath, name)).st_size
            except OSError:
                pass
    return total
