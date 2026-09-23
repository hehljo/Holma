"""
Shared mirror layout and archiving for git-based backup handlers.

Both the GitHub handler and the generic git handler (GitLab, Gitea, Bitbucket,
Codeberg, Forgejo) keep bare mirrors so each run only fetches new objects. A
mirror is working state, not a backup version: it is overwritten in place and
carries no timestamp, so retention has nothing to rotate.

This mixin puts mirrors into a working subdirectory and writes one timestamped
tar.gz per repository next to it. Those archives are what the executor's
retention cleanup matches on, so the configured number of versions is what
actually survives on disk.
"""
import os
import logging
import tarfile

logger = logging.getLogger(__name__)

# Mirrors live here and are excluded from retention by the executor.
MIRROR_DIRNAME = '_mirrors'


class GitMirrorArchiveMixin:
    """Mirror working directory + timestamped per-repository archives."""

    def _mirror_root(self):
        """Directory holding the incremental mirrors. Created on demand."""
        path = os.path.join(self.work_path, MIRROR_DIRNAME)
        os.makedirs(path, exist_ok=True)
        return path

    def _migrate_legacy_mirror(self, repo_dir, new_path):
        """Move a mirror from the old flat layout into the mirror working dir.

        Earlier versions cloned straight into dest_path. Without this the next
        run would clone every repository again from scratch.
        """
        legacy_path = os.path.join(self.work_path, f"{repo_dir}.git")
        if os.path.exists(new_path) or not os.path.isdir(legacy_path):
            return
        try:
            os.replace(legacy_path, new_path)
            self.log(f"Moved existing mirror {repo_dir}.git into {MIRROR_DIRNAME}/")
        except OSError as e:
            self.log(f"WARNING: could not move legacy mirror {repo_dir}.git: {e}")

    def _archive_repository(self, repo, repo_dir, repo_path, timestamp):
        """Write one timestamped tar.gz of the bare mirror.

        gzip rather than zip: a mirror accumulates loose objects between runs,
        and those compress far better as a solid stream than as individually
        deflated zip entries. On an already packed mirror neither format gains
        more than ~3%, so the choice costs nothing there. Restore is a plain
        `git clone <extracted>.git <target>`.

        Returns:
            int: size of the written archive in bytes
        """
        final_path = os.path.join(self.dest_path, f"{repo_dir}_{timestamp}.tar.gz")
        # Build under a name the retention cleanup cannot match, then rename -
        # an interrupted run must never leave a partial file that counts as a
        # kept version.
        tmp_path = os.path.join(self.dest_path, f".{repo_dir}.partial.tar.gz")

        try:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            with tarfile.open(tmp_path, 'w:gz') as tar:
                tar.add(repo_path, arcname=f"{repo_dir}.git")
            os.replace(tmp_path, final_path)
        except Exception as e:
            self.log(f"ERROR: could not archive {repo}: {e}")
            logger.error(f"Archiving {repo} failed: {e}")
            try:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
            except OSError:
                pass
            raise

        size = self._get_file_size(final_path)
        self.log(f"Archived {repo} -> {os.path.basename(final_path)} ({size} bytes)")
        return size
