"""
Generic Git Repository Backup Handler
Best Practice 02/2026: Uses --mirror + remote update (same as github.py),
retry logic with exponential backoff, consistent BackupHandler base
Supports: GitLab, Gitea, Forgejo, Bitbucket, Codeberg, and other Git platforms
"""
import subprocess
import logging
import os
import time
import re
from datetime import datetime
from app.backup.base import BackupHandler
from app.backup.sources.git_archive import GitMirrorArchiveMixin

logger = logging.getLogger(__name__)


class GitBackup(GitMirrorArchiveMixin, BackupHandler):
    """Handles Git repository backups from various platforms using --mirror"""

    # Platform-specific URL templates
    PLATFORMS = {
        'gitlab': 'https://oauth2:{token}@gitlab.com/{repo}.git',
        'gitlab-selfhosted': 'https://oauth2:{token}@{host}/{repo}.git',
        'gitea': 'https://{token}@{host}/{repo}.git',
        'forgejo': 'https://{token}@{host}/{repo}.git',
        'bitbucket': 'https://x-token-auth:{token}@bitbucket.org/{repo}.git',
        'codeberg': 'https://{token}@codeberg.org/{repo}.git',
    }

    def backup(self):
        """Execute Git repository backup using --mirror"""
        repositories = self._as_list(self.source_config.get('repositories'))
        credentials = self.source_config.get('credentials', {})
        platform = self.source_config.get('platform', 'gitlab')
        host = self.source_config.get('host', '')  # For self-hosted instances

        # Get token from direct config or environment/profile references
        token_env = credentials.get('token_env', '')
        token = self.source_config.get('token', '')
        if not token and token_env:
            token = self._get_env_credential(token_env, required=False)

        if not token:
            self.log(f"WARNING: No authentication token for {platform} – public repos only")

        files_synced = 0
        size_synced = 0
        options = self.source_config.get('options', {})

        mirror_root = self._mirror_root()
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

        for repo in repositories:
            try:
                self.log(f"Backing up repository: {repo}")

                # Use .git suffix for mirror repos for clarity
                repo_dir = repo.replace('/', '_')
                repo_path = os.path.join(mirror_root, f"{repo_dir}.git")
                self._migrate_legacy_mirror(repo_dir, repo_path)

                # Build clone/pull URL with token
                repo_url = self._build_repo_url(platform, repo, token, host)

                if os.path.exists(repo_path):
                    # Mirror exists -> update all refs (prune deleted branches)
                    self.log(f"Updating mirror for: {repo}")
                    result = self._run_with_retry(
                        ['git', '-C', repo_path, 'remote', 'update', '--prune'],
                        retries=3
                    )
                else:
                    # Create new mirror clone (all refs, tags, branches, history)
                    self.log(f"Creating mirror clone for: {repo}")
                    result = self._run_with_retry(
                        ['git', 'clone', '--mirror', repo_url, repo_path],
                        retries=3
                    )

                if result.stdout:
                    self.log(self._redact_token(result.stdout, token))
                if result.stderr and 'warning' not in result.stderr.lower():
                    self.log(self._redact_token(result.stderr, token))

                if result.returncode != 0:
                    self.log(f"ERROR: git command returned code {result.returncode}")
                    continue

                files_synced += 1

                # Handle LFS if configured
                if options.get('include_lfs', False):
                    self.log(f"Fetching LFS objects for {repo}")
                    subprocess.run(
                        ['git', '-C', repo_path, 'lfs', 'fetch', '--all'],
                        capture_output=True,
                        timeout=300
                    )

                # Backup wiki if configured and exists
                if options.get('include_wikis', False):
                    wiki_url = repo_url.replace('.git', '.wiki.git')
                    wiki_path = os.path.join(mirror_root, f"{repo_dir}.wiki.git")
                    self._migrate_legacy_mirror(f"{repo_dir}.wiki", wiki_path)

                    try:
                        if os.path.exists(wiki_path):
                            subprocess.run(
                                ['git', '-C', wiki_path, 'remote', 'update', '--prune'],
                                capture_output=True,
                                text=True,
                                timeout=120
                            )
                        else:
                            subprocess.run(
                                ['git', 'clone', '--mirror', wiki_url, wiki_path],
                                capture_output=True,
                                text=True,
                                timeout=120
                            )
                        self.log(f"Wiki backed up for {repo}")
                    except Exception:
                        self.log(f"No wiki found for {repo}")

                # One timestamped archive per repository - this is what
                # retention rotates; the mirror stays outside versioning.
                size_synced += self._archive_repository(
                    repo, repo_dir, repo_path, timestamp
                )

            except subprocess.TimeoutExpired:
                self.log(f"ERROR: Timeout backing up {repo}")
                logger.error(f"Timeout backing up {repo}")
            except Exception as e:
                self.log(f"ERROR backing up {repo}: {str(e)}")
                logger.error(f"Error backing up {repo}: {e}")

        return {
            'files_synced': files_synced,
            'size_synced': size_synced,
            'logs': self.get_logs()
        }

    def _redact_token(self, text, token):
        """Remove credential material from git output before logging."""
        if not text or not token:
            return text
        redacted = text.replace(token, '***REDACTED***')
        return re.sub(r'https://[^@\s]+@', 'https://***REDACTED***@', redacted)

    def _build_repo_url(self, platform, repo, token, host=''):
        """Build repository URL based on platform"""
        if platform == 'gitlab-selfhosted' and host:
            return f"https://oauth2:{token}@{host}/{repo}.git"
        elif platform in ['gitea', 'forgejo'] and host:
            return f"https://{token}@{host}/{repo}.git"
        elif platform == 'gitlab':
            return f"https://oauth2:{token}@gitlab.com/{repo}.git"
        elif platform == 'bitbucket':
            return f"https://x-token-auth:{token}@bitbucket.org/{repo}.git"
        elif platform == 'codeberg':
            return f"https://{token}@codeberg.org/{repo}.git"
        else:
            # Generic format
            return f"https://{token}@{host}/{repo}.git"

    def _run_with_retry(self, cmd, retries=3, timeout=300):
        """Run command with exponential backoff retry"""
        last_result = None
        for attempt in range(retries):
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=timeout
            )
            if result.returncode == 0:
                return result
            last_result = result
            if attempt < retries - 1:
                wait_time = 2 ** attempt
                self.log(f"Retry {attempt + 1}/{retries} in {wait_time}s...")
                time.sleep(wait_time)
        return last_result


# Platform-specific convenience classes
class GitLabBackup(GitBackup):
    """GitLab repository backup handler"""
    def __init__(self, source_config, dest_path):
        if 'platform' not in source_config:
            source_config['platform'] = 'gitlab'
        super().__init__(source_config, dest_path)


class GiteaBackup(GitBackup):
    """Gitea repository backup handler"""
    def __init__(self, source_config, dest_path):
        if 'platform' not in source_config:
            source_config['platform'] = 'gitea'
        super().__init__(source_config, dest_path)


class ForgejoBackup(GitBackup):
    """Forgejo repository backup handler"""
    def __init__(self, source_config, dest_path):
        if 'platform' not in source_config:
            source_config['platform'] = 'forgejo'
        super().__init__(source_config, dest_path)


class BitbucketBackup(GitBackup):
    """Bitbucket repository backup handler"""
    def __init__(self, source_config, dest_path):
        if 'platform' not in source_config:
            source_config['platform'] = 'bitbucket'
        super().__init__(source_config, dest_path)


class CodebergBackup(GitBackup):
    """Codeberg repository backup handler"""
    def __init__(self, source_config, dest_path):
        if 'platform' not in source_config:
            source_config['platform'] = 'codeberg'
        super().__init__(source_config, dest_path)
