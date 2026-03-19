"""Checkpoint system for resumable data collection."""

import json
import os
import logging
from datetime import datetime
from typing import Dict

logger = logging.getLogger(__name__)


class Checkpoint:
    """Manage checkpoint state for resumable queries."""

    def __init__(self, checkpoint_file: str = "output/checkpoint.json"):
        """Initialize checkpoint."""
        self.checkpoint_file = checkpoint_file
        self.state = self._load()

    def _load(self) -> Dict:
        """Load checkpoint from file or create fresh state."""
        if not os.path.exists(self.checkpoint_file):
            return self._new_state()

        try:
            with open(self.checkpoint_file, "r") as f:
                state = json.load(f)
            self._log_loaded_state(state)
            return state
        except Exception as e:
            logger.warning(f"Could not load checkpoint: {e}, starting fresh")
            return self._new_state()

    def _new_state(self) -> Dict:
        """Create a fresh checkpoint state."""
        return {
            "created_at": datetime.utcnow().isoformat(),
            "processed_repos": {"github": [], "bitbucket": []},
            "developer_count": 0,
        }

    def _log_loaded_state(self, state: Dict) -> None:
        """Log information about loaded checkpoint."""
        github_count = len(state.get("processed_repos", {}).get("github", []))
        bitbucket_count = len(state.get("processed_repos", {}).get("bitbucket", []))
        logger.info(f"Loaded checkpoint: {github_count} GitHub repos, {bitbucket_count} Bitbucket repos")

    def save(self) -> None:
        """Save checkpoint to file."""
        self.state["updated_at"] = datetime.utcnow().isoformat()
        os.makedirs(os.path.dirname(self.checkpoint_file), exist_ok=True)
        try:
            with open(self.checkpoint_file, "w") as f:
                json.dump(self.state, f, indent=2)
            logger.debug(f"Checkpoint saved: {self.checkpoint_file}")
        except Exception as e:
            logger.error(f"Failed to save checkpoint: {e}")

    def is_processed(self, platform: str, owner_or_project: str, repo_name_or_slug: str) -> bool:
        """Check if a repository has been processed."""
        repo_key = f"{owner_or_project}/{repo_name_or_slug}"
        processed_list = self.state.get("processed_repos", {}).get(platform, [])
        return repo_key in processed_list

    def mark_processed(self, platform: str, owner_or_project: str, repo_name_or_slug: str) -> None:
        """Mark a repository as processed."""
        repo_key = f"{owner_or_project}/{repo_name_or_slug}"
        processed_list = self.state["processed_repos"][platform]
        if repo_key not in processed_list:
            processed_list.append(repo_key)

    def update_developer_count(self, count: int) -> None:
        """Update total developer count."""
        self.state["developer_count"] = count

    def clear(self) -> None:
        """Clear all checkpoint state."""
        self.state = self._new_state()
        logger.info("Checkpoint cleared")

    def is_github_repo_processed(self, owner: str, repo: str) -> bool:
        """Convenience method to check if a GitHub repo has been processed."""
        return self.is_processed("github", owner, repo)

    def mark_github_repo_processed(self, owner: str, repo: str) -> None:
        """Convenience method to mark a GitHub repo as processed."""
        self.mark_processed("github", owner, repo)

    def is_bitbucket_repo_processed(self, project_key: str, repo_slug: str) -> bool:
        """Convenience method to check if a Bitbucket repo has been processed."""
        return self.is_processed("bitbucket", project_key, repo_slug)

    def mark_bitbucket_repo_processed(self, project_key: str, repo_slug: str) -> None:
        """Convenience method to mark a Bitbucket repo as processed."""
        self.mark_processed("bitbucket", project_key, repo_slug)

    def get_summary(self) -> Dict[str, int]:
        """Get summary of processed items."""
        return {
            "github": len(self.state.get("processed_repos", {}).get("github", [])),
            "bitbucket": len(self.state.get("processed_repos", {}).get("bitbucket", [])),
            "developers": self.state.get("developer_count", 0),
        }

    def get_processed_count(self) -> Dict[str, int]:
        """
        Get processed count in the format expected by main.py.

        Returns:
            Dictionary with keys 'github', 'bitbucket', 'developers'
        """
        return self.get_summary()
