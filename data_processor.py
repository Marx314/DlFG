"""Data processing and enrichment for developer inventory."""

import logging
from typing import Dict, List, Tuple, Optional
from config import (
    TECH_EXTENSIONS,
    MIN_COMMITS,
    TRAINING_FIT_COMMIT_MULTIPLIER,
    TRAINING_FIT_COMMIT_MAX_SCORE,
    TRAINING_FIT_REPO_MULTIPLIER,
    TRAINING_FIT_REPO_MAX_SCORE,
)
from language_detector import LanguageDetector

logger = logging.getLogger(__name__)


class DataProcessor:
    """Process and enrich raw API data into developer profiles."""

    def __init__(self):
        """Initialize data processor."""
        self.developers = {}
        self.language_detector = LanguageDetector()

    def add_developer_data(self, developers: Dict) -> None:
        """
        Merge raw API developer data into processor.

        Args:
            developers: Dictionary of developer data from API queries
        """
        for dev_name, dev_data in developers.items():
            if dev_name not in self.developers:
                self.developers[dev_name] = dev_data
            else:
                # Merge existing and new data
                self._merge_developer(dev_name, dev_data)

    def _merge_developer(self, dev_name: str, new_data: Dict) -> None:
        """
        Merge new developer data with existing.

        Args:
            dev_name: Developer name
            new_data: New developer data to merge
        """
        existing = self.developers[dev_name]

        # Update email if empty
        if not existing.get("email") or existing["email"] == "unknown":
            existing["email"] = new_data.get("email")

        # Add new repositories
        existing_repos = set(existing.get("repositories", []))
        new_repos = set(new_data.get("repositories", []))
        existing["repositories"] = list(existing_repos.union(new_repos))

        # Merge repo platform mappings
        existing_repo_platforms = existing.get("repo_platforms", {})
        new_repo_platforms = new_data.get("repo_platforms", {})
        existing_repo_platforms.update(new_repo_platforms)
        existing["repo_platforms"] = existing_repo_platforms

        # Sum commits
        existing["commits"] = existing.get("commits", 0) + new_data.get("commits", 0)

        # Add platforms if not present
        existing_platforms = set(existing.get("platforms", []))
        new_platforms = set(new_data.get("platforms", []))
        existing["platforms"] = list(existing_platforms.union(new_platforms))

    def calculate_technology_profile(self, dev_name: str) -> Dict[str, int]:
        """
        Calculate technology profile for a developer using language detection.

        Detects actual programming languages from repositories using GitHub's
        linguist API and file extension analysis for Bitbucket.

        Args:
            dev_name: Developer name

        Returns:
            Dictionary mapping language/technology names to usage counts
        """
        if dev_name not in self.developers:
            return {}

        dev_data = self.developers[dev_name]
        repositories = dev_data.get("repositories", [])
        repo_platforms = dev_data.get("repo_platforms", {})

        if not repositories:
            return {}

        # Build repository list with stored platform info
        repo_list_with_platform = []
        for repo in repositories:
            # Use stored platform info, fall back to inference if not found
            platform = repo_platforms.get(repo)
            if not platform:
                platforms = dev_data.get("platforms", [])
                platform = self._infer_platform_from_repo(repo, platforms)
            if platform:
                # Parse owner/project and repo name
                parts = repo.split("/", 1)
                if len(parts) == 2:
                    repo_list_with_platform.append((platform, parts[0], parts[1]))

        if not repo_list_with_platform:
            return {}

        # Get languages across all repositories
        return self.language_detector.get_developer_languages(repo_list_with_platform)

    def _infer_platform_from_repo(
        self, repo: str, platforms: List[str]
    ) -> Optional[str]:
        """
        Infer platform from repository name pattern and available platforms.

        Args:
            repo: Repository name (owner/repo or PROJECT_KEY/repo)
            platforms: List of platforms the developer is active on

        Returns:
            Platform name or None
        """
        # If only one platform, use it
        if len(platforms) == 1:
            return platforms[0].lower()

        # Try to infer from repo format
        # GitHub repos tend to have lowercase owner/repo
        # Bitbucket repos often have uppercase PROJECT_KEY/repo
        owner_or_project = repo.split("/")[0]
        if owner_or_project.isupper() and len(owner_or_project) <= 6:
            # Likely Bitbucket project key (usually caps, short)
            if "Bitbucket" in platforms:
                return "bitbucket"
        elif "GitHub" in platforms:
            return "github"

        # Default to first platform if can't infer
        return platforms[0].lower() if platforms else None

    def calculate_training_fit_score(self, dev_name: str) -> float:
        """
        Calculate training fit score (0-100) for Secure Code Warrior training.

        Simple scoring based on:
        - Commit frequency (active developer indicator)
        - Repository diversity (breadth of work)

        Args:
            dev_name: Developer name

        Returns:
            Training fit score (0-100)
        """
        if dev_name not in self.developers:
            return 0.0

        dev_data = self.developers[dev_name]
        commits = dev_data.get("commits", 0)
        repos = len(dev_data.get("repositories", []))

        if commits == 0:
            return 0.0

        # Commit frequency score (configurable max score)
        commit_score = min(
            commits * TRAINING_FIT_COMMIT_MULTIPLIER,
            TRAINING_FIT_COMMIT_MAX_SCORE,
        )

        # Repository diversity score (configurable max score)
        repo_score = min(repos * TRAINING_FIT_REPO_MULTIPLIER, TRAINING_FIT_REPO_MAX_SCORE)

        return min(commit_score + repo_score, 100.0)

    def get_summary_stats(self) -> Dict:
        """
        Get summary statistics for the inventory.

        Returns:
            Dictionary with summary stats
        """
        total_devs = len(self.developers)
        total_commits = sum(d.get("commits", 0) for d in self.developers.values())
        avg_commits = total_commits / total_devs if total_devs > 0 else 0

        all_techs = set()
        for dev_data in self.developers.values():
            all_techs.update(self.calculate_technology_profile(dev_data.get("name", "")).keys())

        scores = [self.calculate_training_fit_score(dev) for dev in self.developers.keys()]
        avg_score = sum(scores) / len(scores) if scores else 0

        return {
            "total_developers": total_devs,
            "total_commits": total_commits,
            "avg_commits_per_dev": round(avg_commits, 2),
            "unique_technologies": len(all_techs),
            "avg_training_fit_score": round(avg_score, 2),
        }
