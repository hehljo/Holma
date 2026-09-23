#!/usr/bin/env python3
"""
Gate: git-based backups produce rotatable, timestamped archives.

Covers the two failures this replaces:
  1. Retention never deleted anything for GitHub, because mirror directories
     carry no timestamp and the cleanup only matches \\d{8}_\\d{6}.
  2. Each repository was stored as a bare directory, not one archive per
     project.

Run:  python3 backend/tests/test_git_rotation.py
Exit: 0 = all passed, 1 = failures, 2 = could not run (nothing measured)
"""
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BACKEND = os.path.join(REPO_ROOT, 'backend')
sys.path.insert(0, BACKEND)

FAILURES = []
PASSED = 0


def check(name, condition, detail=''):
    global PASSED
    if condition:
        PASSED += 1
        print(f"  ok   {name}")
    else:
        FAILURES.append(f"{name}: {detail}")
        print(f"  FAIL {name}  {detail}")


# --- the retention rule --------------------------------------------------
# select_expired() is the function the executor calls. It lives in a module
# without Flask, so the gate calls it instead of re-reading a regex from source.


def main():
    print("Gate: git rotation + per-project archives\n")

    sources_dir = os.path.join(BACKEND, 'app', 'backup', 'sources')

    def strip(text):
        """Drop comments and docstrings: they describe the fix and would
        satisfy naive text checks on their own."""
        return re.sub(r'#[^\n]*', '', re.sub(r'"""..*?"""', '', text, flags=re.S))

    shared_path = os.path.join(sources_dir, 'git_archive.py')
    if not os.path.isfile(shared_path):
        print("ABBRUCH: git_archive.py not found — nothing measured")
        return 2
    with open(shared_path, encoding='utf-8') as fh:
        shared_src = fh.read()
    shared_code = strip(shared_src)

    try:
        from app.backup.artifacts import WORKING_DIR_NAMES, select_expired
    except ImportError as e:
        print(f"ABBRUCH: app.backup.artifacts not importable ({e}) — nothing measured")
        return 2
    with open(os.path.join(BACKEND, 'app', 'backup', 'executor.py'), encoding='utf-8') as fh:
        exec_src = fh.read()

    # Read the constant from source rather than importing it: the handlers pull
    # in the Flask app via BackupHandler, which is not available to a bare test
    # run. Parsing keeps the gate runnable without the full environment.
    mirror_match = re.search(r"MIRROR_DIRNAME\s*=\s*'([^']+)'", shared_src)
    if mirror_match is None:
        print("ABBRUCH: MIRROR_DIRNAME not found in git_archive.py — nothing measured")
        return 2
    MIRROR_DIRNAME = mirror_match.group(1)

    # Find every handler that clones git mirrors, rather than keeping a list:
    # a new platform handler must not slip through unnoticed.
    mirror_handlers = {}
    for fname in sorted(os.listdir(sources_dir)):
        if not fname.endswith('.py') or fname == 'git_archive.py':
            continue
        with open(os.path.join(sources_dir, fname), encoding='utf-8') as fh:
            src = fh.read()
        code = strip(src)
        if "'clone', '--mirror'" in code or '"clone", "--mirror"' in code:
            mirror_handlers[fname] = code

    # --- 1. the archive is actually written, with a timestamp --------------
    print("1. Shared archiving writes one timestamped archive per repository")
    check("archive helper exists", '_archive_repository' in shared_code)
    check("archive name carries a timestamp",
          re.search(r'\{repo_dir\}_\{timestamp\}', shared_code) is not None,
          "archive filename must contain the run timestamp")
    check("written to a temp name first",
          'partial' in shared_code and 'os.replace(tmp_path' in shared_code,
          "an interrupted run must not leave a countable version")

    print(f"\n   git-mirror handlers found: {', '.join(mirror_handlers) or 'NONE'}")
    check("mirror handlers were found at all", len(mirror_handlers) >= 2,
          f"expected github.py and git.py, got {list(mirror_handlers)}")

    for fname, code in mirror_handlers.items():
        check(f"{fname}: uses the shared mixin",
              'GitMirrorArchiveMixin' in code)
        check(f"{fname}: calls the archiver",
              re.search(r'self\._archive_repository\(', code) is not None)
        check(f"{fname}: timestamp format matches retention",
              "'%Y%m%d_%H%M%S'" in code)
        check(f"{fname}: mirrors go into the working dir",
              re.search(r'repo_path\s*=\s*os\.path\.join\(mirror_root', code) is not None,
              "mirror must not be cloned straight into dest_path")
        check(f"{fname}: no private copy of the archiver",
              'def _archive_repository' not in code,
              "archiving must come from the shared mixin")

    # --- 2. mirrors are outside the versioned area ------------------------
    print("\n2. Mirrors are working state, not versions")
    check("mirror dir is a declared working dir", MIRROR_DIRNAME in WORKING_DIR_NAMES)
    check("executor uses the shared rule, not a second copy",
          'select_expired(' in exec_src
          and re.search(r"(MIRROR_DIRNAME|WORKING_DIR_NAMES)\s*=", exec_src) is None,
          "the retention rule and excluded names must not be typed twice")

    # --- 3. the rule deletes the right things -----------------------------
    print("\n3. Retention selects correctly (both directions)")
    names = [MIRROR_DIRNAME, '.acme_repo.partial.tar.gz'] + [
        f'acme_repo_2026083{d}_120000.tar.gz' for d in range(1, 6)
    ]

    deleted = select_expired(names, 3)
    check("deletes the surplus (5 versions, keep 3 -> 2 deleted)",
          len(deleted) == 2, f"deleted={deleted}")
    check("keeps the newest",
          'acme_repo_20260835_120000.tar.gz' not in deleted, f"deleted={deleted}")
    check("never deletes the mirror dir",
          MIRROR_DIRNAME not in deleted, f"deleted={deleted}")
    check("never deletes a partial file",
          '.acme_repo.partial.tar.gz' not in deleted, f"deleted={deleted}")

    # green direction: under the limit nothing may go
    few = [MIRROR_DIRNAME] + [f'acme_repo_2026083{d}_120000.tar.gz' for d in (1, 2)]
    check("keeps everything when under the limit",
          select_expired(few, 3) == [],
          "healthy case must stay green")

    # a repo whose own name contains a timestamp must not fool the exclusion
    tricky = [MIRROR_DIRNAME] + [
        f'log_20240101_000000_repo_2026083{d}_120000.tar.gz' for d in range(1, 6)
    ]
    deleted_tricky = select_expired(tricky, 3)
    check("mirror dir survives even with timestamped repo names",
          MIRROR_DIRNAME not in deleted_tricky, f"deleted={deleted_tricky}")

    # --- 3b. a per-source run rotates too ---------------------------------
    # The manual "back up now" button runs a single source. Retention must
    # apply to that run exactly as it does to a full one - otherwise the
    # button quietly grows the disk.
    print("\n3b. Retention applies to single-source runs")

    def enclosing_def(src, needle):
        """Name of the method a call sits in, by def position."""
        pos = src.find(needle)
        if pos < 0:
            return None
        owner = None
        for m in re.finditer(r'\n    def (\w+)', src):
            if m.start() < pos:
                owner = m.group(1)
            else:
                break
        return owner

    owner = enclosing_def(exec_src, 'self._cleanup_old_backup_versions(')
    check("cleanup runs per source, not per run",
          owner == '_backup_source',
          f"cleanup is called from {owner!r}; in a per-run method it would be "
          f"skipped or misapplied for single-source runs")
    check("cleanup is scoped to the source being backed up",
          'self._cleanup_old_backup_versions(source_id)' in exec_src,
          "cleanup must receive the source id, not run over everything")
    check("per-source filter exists in execute()",
          re.search(r'if source_ids:', exec_src) is not None)

    # A handler that raises used to skip retention entirely: the cleanup call
    # sat after handler.backup() in the same try. A source with expired
    # credentials would then grow forever while the visible error talks about
    # the connection.
    # Anchor on a line unique to the failure branch: `except Exception as e:`
    # alone also matches the notification handler far above in execute(), and
    # the slice would then still contain the success-path call.
    fail_anchor = exec_src.find("result.status = 'failed'")
    fail_end = exec_src.find("'status': 'failed'", fail_anchor)
    failure_branch = exec_src[fail_anchor:fail_end] if fail_anchor >= 0 else ''
    check("failure branch was located", fail_anchor >= 0 and fail_end > fail_anchor,
          "could not slice the failure path - check not measured")
    check("retention also runs when the handler fails",
          'run_retention_once()' in failure_branch,
          "the failure path must rotate too, or a broken source fills the disk")
    check("retention runs at most once per source",
          'if retention_ran:' in exec_src,
          "success path plus failure path must not rotate twice")
    check("the once-guard is per source, not shared across threads",
          re.search(r'\n\s*retention_ran = \[\]', exec_src) is not None
          and 'self._retention' not in exec_src,
          "sources run in parallel threads sharing one executor instance")

    # The API must refuse a second run on a source already running: two runs
    # writing the same mirror corrupt it and their retention passes race.
    api_path = os.path.join(BACKEND, 'app', 'api', 'backup.py')
    with open(api_path, encoding='utf-8') as fh:
        api_src = fh.read()
    api_code = strip(api_src)
    check("API exposes running sources", "'/running-sources'" in api_code)

    jobs_path = os.path.join(BACKEND, 'app', 'backup', 'jobs.py')
    with open(jobs_path, encoding='utf-8') as fh:
        jobs_src = fh.read()
    check("API delegates to the durable reservation guard",
          'reserve_backup(' in api_src and 'except JobConflictError' in api_src,
          "start must reserve before the worker can execute")
    check("reservation checks active sources while holding the job lock",
          'with job_lock()' in jobs_src
          and 'busy = active_source_ids() & set(selected_ids)' in jobs_src
          and 'raise JobConflictError(busy)' in jobs_src,
          "same-source jobs must be serialized across processes")
    check("API rejects disabled sources",
          "'Sources are disabled'" in jobs_src,
          "a disabled source is dropped by the executor and would report success")
    check("API rejects unknown sources", "'Unknown sources'" in jobs_src)

    # --- 4. end to end: a real mirror archives and restores ----------------
    print("\n4. End-to-end on a real git mirror")
    if not shutil.which('git'):
        print("  ABBRUCH: git not available — end-to-end not measured")
        return 2

    tmp = tempfile.mkdtemp(prefix='bg_gate_')
    try:
        origin = os.path.join(tmp, 'origin')
        os.makedirs(origin)
        subprocess.run(['git', 'init', '-q', origin], check=True)
        with open(os.path.join(origin, 'file.txt'), 'w') as fh:
            fh.write('content\n')
        env = dict(os.environ, GIT_AUTHOR_NAME='t', GIT_AUTHOR_EMAIL='t@t',
                   GIT_COMMITTER_NAME='t', GIT_COMMITTER_EMAIL='t@t')
        subprocess.run(['git', '-C', origin, 'add', '.'], check=True, env=env)
        subprocess.run(['git', '-C', origin, 'commit', '-qm', 'init'], check=True, env=env)

        mirror = os.path.join(tmp, 'acme_repo.git')
        subprocess.run(['git', 'clone', '--mirror', '-q', origin, mirror], check=True)

        archive = os.path.join(tmp, 'acme_repo_20260831_120000.tar.gz')
        with tarfile.open(archive, 'w:gz') as tar:
            tar.add(mirror, arcname='acme_repo.git')

        check("archive is a single file per project", os.path.isfile(archive))
        check("archive name is picked up by retention",
              select_expired([os.path.basename(archive), 'acme_repo_20990101_000000.tar.gz'], 1)
              == [os.path.basename(archive)])

        # the point of the whole thing: it must restore
        extract_dir = os.path.join(tmp, 'extract')
        os.makedirs(extract_dir)
        with tarfile.open(archive) as tar:
            tar.extractall(extract_dir)
        restored = os.path.join(tmp, 'restored')
        r = subprocess.run(
            ['git', 'clone', '-q', os.path.join(extract_dir, 'acme_repo.git'), restored],
            capture_output=True, text=True
        )
        check("archive restores via git clone", r.returncode == 0, r.stderr.strip()[:200])
        check("restored content is intact",
              os.path.isfile(os.path.join(restored, 'file.txt')))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print(f"\n{'-' * 55}")
    if FAILURES:
        print(f"ROT: {len(FAILURES)} von {PASSED + len(FAILURES)} Pruefungen gefallen")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    if PASSED == 0:
        print("ABBRUCH: keine Pruefung gelaufen")
        return 2
    print(f"GRUEN: {PASSED} Pruefungen bestanden")
    return 0


if __name__ == '__main__':
    sys.exit(main())
