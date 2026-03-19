"""Repository exclusion identification and filtering with time-based tracking."""

import json
import logging
import os
from typing import List, Dict, Optional
from datetime import datetime
from fnmatch import fnmatch

logger = logging.getLogger(__name__)

EXCLUDED_REPOS_FILE = os.getenv("EXCLUDED_REPOS_FILE", "excluded_repos.json")


class ExcludedRepoFilter:
    """Manage and filter QA repositories from analysis."""

    def __init__(self, config_file: str = None):
        """
        Initialize excluded repository filter.

        Args:
            config_file: Path to excluded repos configuration file
        """
        self.config_file = config_file or EXCLUDED_REPOS_FILE
        self.excluded_repos = []
        self._load_config()

    def _load_config(self) -> None:
        """Load excluded repositories from configuration file."""
        if not os.path.exists(self.config_file):
            logger.info(f"No excluded repos config found: {self.config_file}")
            return

        try:
            with open(self.config_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.excluded_repos = data.get("repositories", [])
            logger.info(f"Loaded {len(self.excluded_repos)} excluded repository rules from {self.config_file}")
        except Exception as e:
            logger.warning(f"Failed to load QA repos config: {e}")

    def is_excluded_repo(self, platform: str, owner: str, repo_name: str) -> bool:
        """
        Check if a repository should be excluded from analysis.

        Args:
            platform: Repository platform ('github' or 'bitbucket')
            owner: Repository owner/workspace
            repo_name: Repository name

        Returns:
            True if repo is excluded, False otherwise
        """
        for qa_rule in self.excluded_repos:
            # Check platform
            if qa_rule.get("platform", "").lower() != platform.lower():
                continue

            # Check owner/workspace (optional - can be partial match)
            rule_owner = qa_rule.get("owner", "").strip()
            if rule_owner and not self._owner_matches(owner, rule_owner):
                continue

            # Check repo pattern (supports wildcards)
            repo_pattern = qa_rule.get("repo_pattern", "").strip()
            if repo_pattern and fnmatch(repo_name.lower(), repo_pattern.lower()):
                logger.debug(
                    f"Excluded {platform}/{owner}/{repo_name} "
                    f"(rule: {repo_pattern}, added: {qa_rule.get('added_date')})"
                )
                return True

            # Also check specific name
            repo_name_exact = qa_rule.get("repo_name", "").strip()
            if repo_name_exact and repo_name_exact.lower() == repo_name.lower():
                logger.debug(
                    f"Excluded {platform}/{owner}/{repo_name} "
                    f"(exact match, added: {qa_rule.get('added_date')})"
                )
                return True

        return False

    def _owner_matches(self, owner: str, rule_owner: str) -> bool:
        """
        Check if owner matches rule (supports wildcards).

        Args:
            owner: Actual owner/workspace
            rule_owner: Rule pattern

        Returns:
            True if matches
        """
        return fnmatch(owner.lower(), rule_owner.lower())

    def add_excluded_repo(
        self,
        platform: str,
        owner: str,
        repo_pattern: str,
        reason: str = "",
        repo_name: str = None
    ) -> None:
        """
        Add an excluded repository rule.

        Args:
            platform: 'github' or 'bitbucket'
            owner: Repository owner/workspace
            repo_pattern: Repository name pattern (supports wildcards like *-qa)
            reason: Reason for excluding from training
            repo_name: Exact repository name (alternative to pattern)
        """
        rule = {
            "platform": platform.lower(),
            "owner": owner,
            "repo_pattern": repo_pattern if repo_pattern else None,
            "repo_name": repo_name,
            "added_date": datetime.now().strftime("%Y-%m-%d"),
            "reason": reason,
        }

        self.excluded_repos.append(rule)
        self._save_config()
        logger.info(f"Added excluded repo rule: {platform}/{owner}/{repo_pattern or repo_name}")

    def remove_excluded_repo(
        self,
        platform: str,
        owner: str,
        repo_pattern: str = None,
        repo_name: str = None
    ) -> bool:
        """
        Remove an excluded repository rule.

        Args:
            platform: 'github' or 'bitbucket'
            owner: Repository owner/workspace
            repo_pattern: Repository pattern to match
            repo_name: Exact repository name

        Returns:
            True if removed, False if not found
        """
        original_count = len(self.excluded_repos)

        self.excluded_repos = [
            r for r in self.excluded_repos
            if not (
                r.get("platform", "").lower() == platform.lower()
                and r.get("owner", "").lower() == owner.lower()
                and (
                    (repo_pattern and r.get("repo_pattern", "").lower() == repo_pattern.lower())
                    or (repo_name and r.get("repo_name", "").lower() == repo_name.lower())
                )
            )
        ]

        if len(self.excluded_repos) < original_count:
            self._save_config()
            logger.info(f"Removed excluded repo rule: {platform}/{owner}/{repo_pattern or repo_name}")
            return True

        return False

    def _save_config(self) -> None:
        """Save QA repositories configuration to file."""
        try:
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump({"repositories": self.excluded_repos}, f, indent=2)
            logger.info(f"Saved excluded repos config to {self.config_file}")
        except Exception as e:
            logger.error(f"Failed to save excluded repos config: {e}")

    def get_excluded_repos(self) -> List[Dict]:
        """
        Get list of all excluded repository rules.

        Returns:
            List of excluded repository rules with timestamps
        """
        return self.excluded_repos

    def get_excluded_repos_by_platform(self, platform: str) -> List[Dict]:
        """
        Get excluded repository rules for a specific platform.

        Args:
            platform: 'github' or 'bitbucket'

        Returns:
            Filtered list of excluded repository rules
        """
        return [r for r in self.excluded_repos if r.get("platform", "").lower() == platform.lower()]

    def get_excluded_repos_added_since(self, date_str: str) -> List[Dict]:
        """
        Get excluded repository rules added since a specific date.

        Args:
            date_str: Date in YYYY-MM-DD format

        Returns:
            Filtered list of excluded repository rules
        """
        return [r for r in self.excluded_repos if r.get("added_date", "") >= date_str]
