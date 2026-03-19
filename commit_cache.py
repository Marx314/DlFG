"""Persistent commit caching for fast reruns."""

import json
import logging
import os
from typing import Dict, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class CommitCache:
    """Cache commit data from GitHub and Bitbucket APIs for fast reruns."""

    def __init__(self, cache_dir: str = "output/commit_cache", enabled: bool = True):
        """
        Initialize commit cache.

        Args:
            cache_dir: Directory to store cache files
            enabled: Whether caching is enabled
        """
        self.cache_dir = cache_dir
        self.enabled = enabled
        self.metadata_file = os.path.join(cache_dir, "metadata.json")
        self.metadata = self._load_metadata()
        self.stats = {
            "cache_hits": 0,
            "cache_misses": 0,
            "commits_cached": 0,
        }

    def _load_metadata(self) -> Dict:
        """Load metadata about cached repos from metadata file."""
        if not self.enabled or not os.path.exists(self.metadata_file):
            return {"cached_repos": {}, "stats": {"cache_hits": 0, "cache_misses": 0}}

        try:
            with open(self.metadata_file, "r") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Could not load cache metadata: {e}, starting fresh")
            return {"cached_repos": {}, "stats": {"cache_hits": 0, "cache_misses": 0}}

    def _get_cache_key(self, platform: str, owner_or_project: str, repo_name_or_slug: str) -> str:
        """
        Generate cache key for a repository.

        Args:
            platform: 'github' or 'bitbucket'
            owner_or_project: GitHub org or Bitbucket project key
            repo_name_or_slug: Repository name/slug

        Returns:
            Cache key like "github:myorg/repo"
        """
        return f"{platform.lower()}:{owner_or_project}/{repo_name_or_slug}"

    def _get_cache_file(self, platform: str, owner_or_project: str, repo_name_or_slug: str) -> str:
        """
        Generate cache file path.

        Returns:
            Path like "output/commit_cache/github__myorg__repo.json"
        """
        key = self._get_cache_key(platform, owner_or_project, repo_name_or_slug)
        # Replace special chars for safe filename
        safe_key = key.replace(":", "__").replace("/", "__").replace("-", "_")
        return os.path.join(self.cache_dir, f"{safe_key}.json")

    def is_cached(self, platform: str, owner_or_project: str, repo_name_or_slug: str) -> bool:
        """
        Check if a repository's commits are cached.

        Args:
            platform: 'github' or 'bitbucket'
            owner_or_project: GitHub org or Bitbucket project key
            repo_name_or_slug: Repository name/slug

        Returns:
            True if fully cached, False otherwise
        """
        if not self.enabled:
            return False

        cache_key = self._get_cache_key(platform, owner_or_project, repo_name_or_slug)
        cached_repo = self.metadata.get("cached_repos", {}).get(cache_key, {})

        # Check if cached and marked as completed
        return cached_repo.get("completed", False)

    def get_cached_commits(
        self, platform: str, owner_or_project: str, repo_name_or_slug: str
    ) -> Optional[List[Dict]]:
        """
        Retrieve cached commits for a repository.

        Args:
            platform: 'github' or 'bitbucket'
            owner_or_project: GitHub org or Bitbucket project key
            repo_name_or_slug: Repository name/slug

        Returns:
            List of commit dicts if cached, None otherwise
        """
        if not self.enabled or not self.is_cached(platform, owner_or_project, repo_name_or_slug):
            self.stats["cache_misses"] += 1
            return None

        cache_file = self._get_cache_file(platform, owner_or_project, repo_name_or_slug)

        try:
            with open(cache_file, "r") as f:
                commits = json.load(f)
            self.stats["cache_hits"] += 1
            logger.debug(
                f"Cache hit: {platform}/{owner_or_project}/{repo_name_or_slug} ({len(commits)} commits)"
            )
            return commits
        except Exception as e:
            logger.warning(f"Could not read cache file {cache_file}: {e}")
            self.stats["cache_misses"] += 1
            return None

    def cache_commits(
        self,
        platform: str,
        owner_or_project: str,
        repo_name_or_slug: str,
        commits: List[Dict],
    ) -> None:
        """
        Store fetched commits in cache.

        Args:
            platform: 'github' or 'bitbucket'
            owner_or_project: GitHub org or Bitbucket project key
            repo_name_or_slug: Repository name/slug
            commits: List of commit dictionaries to cache
        """
        if not self.enabled or not commits:
            return

        os.makedirs(self.cache_dir, exist_ok=True)
        cache_file = self._get_cache_file(platform, owner_or_project, repo_name_or_slug)
        cache_key = self._get_cache_key(platform, owner_or_project, repo_name_or_slug)

        try:
            # Write commits to cache file
            with open(cache_file, "w") as f:
                json.dump(commits, f, indent=2)

            # Update metadata
            if "cached_repos" not in self.metadata:
                self.metadata["cached_repos"] = {}

            self.metadata["cached_repos"][cache_key] = {
                "commit_count": len(commits),
                "cached_at": datetime.utcnow().isoformat() + "Z",
                "completed": True,
            }

            self.stats["commits_cached"] += len(commits)

            logger.debug(
                f"Cached {len(commits)} commits for {platform}/{owner_or_project}/{repo_name_or_slug}"
            )
            self._save_metadata()

        except Exception as e:
            logger.warning(f"Could not cache commits to {cache_file}: {e}")

    def clear_all(self) -> None:
        """Delete entire commit cache."""
        if not self.enabled:
            return

        try:
            if os.path.exists(self.cache_dir):
                import shutil
                shutil.rmtree(self.cache_dir)
                self.metadata = {"cached_repos": {}, "stats": {"cache_hits": 0, "cache_misses": 0}}
                self.stats = {
                    "cache_hits": 0,
                    "cache_misses": 0,
                    "commits_cached": 0,
                }
                logger.info(f"Cleared commit cache directory: {self.cache_dir}")
        except Exception as e:
            logger.warning(f"Could not clear cache directory {self.cache_dir}: {e}")

    def clear_repo(self, platform: str, owner_or_project: str, repo_name_or_slug: str) -> None:
        """Clear cache for a specific repository."""
        if not self.enabled:
            return

        cache_file = self._get_cache_file(platform, owner_or_project, repo_name_or_slug)
        cache_key = self._get_cache_key(platform, owner_or_project, repo_name_or_slug)

        try:
            if os.path.exists(cache_file):
                os.remove(cache_file)

            if cache_key in self.metadata.get("cached_repos", {}):
                del self.metadata["cached_repos"][cache_key]
                self._save_metadata()

            logger.debug(f"Cleared cache for {platform}/{owner_or_project}/{repo_name_or_slug}")
        except Exception as e:
            logger.warning(f"Could not clear cache for {cache_key}: {e}")

    def _save_metadata(self) -> None:
        """Save metadata to metadata file."""
        if not self.enabled:
            return

        try:
            os.makedirs(self.cache_dir, exist_ok=True)
            with open(self.metadata_file, "w") as f:
                json.dump(self.metadata, f, indent=2)
        except Exception as e:
            logger.warning(f"Could not save cache metadata: {e}")

    def get_stats(self) -> Dict:
        """
        Get cache statistics.

        Returns:
            Dictionary with cache stats
        """
        return {
            "cache_hits": self.stats["cache_hits"],
            "cache_misses": self.stats["cache_misses"],
            "total_requests": self.stats["cache_hits"] + self.stats["cache_misses"],
            "cached_repos": len(self.metadata.get("cached_repos", {})),
            "total_cached_commits": sum(
                repo.get("commit_count", 0)
                for repo in self.metadata.get("cached_repos", {}).values()
            ),
            "enabled": self.enabled,
        }
