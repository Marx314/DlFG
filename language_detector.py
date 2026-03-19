"""Language detection for repositories using GitHub's API and file extension analysis."""

import logging
from typing import Dict, List, Tuple
from github_client import GitHubClient
from bitbucket_client import BitbucketClient
from config import BITBUCKET_LANGUAGE_DIVISOR

logger = logging.getLogger(__name__)

# File extension to language mappings (for Bitbucket and fallback)
EXTENSION_TO_LANGUAGE = {
    # Web
    "js": "JavaScript", "jsx": "JavaScript",
    "ts": "TypeScript", "tsx": "TypeScript",
    "html": "HTML", "css": "CSS", "scss": "SCSS",
    "sass": "Sass", "less": "Less",
    # Backend
    "py": "Python", "java": "Java", "cs": "C#",
    "cpp": "C++", "c": "C", "go": "Go", "rs": "Rust",
    "rb": "Ruby", "php": "PHP", "swift": "Swift", "kt": "Kotlin",
    # Data
    "sql": "SQL", "r": "R", "scala": "Scala",
    # Markup/Config
    "json": "JSON", "yaml": "YAML", "yml": "YAML",
    "xml": "XML", "toml": "TOML",
    "markdown": "Markdown", "md": "Markdown",
    "sh": "Shell", "bash": "Shell", "dockerfile": "Docker",
    # DevOps
    "tf": "Terraform", "hcl": "HCL",
}


class LanguageDetector:
    """Detect programming languages in repositories."""

    def __init__(self):
        """Initialize language detector."""
        self._github_client = None
        self._bitbucket_client = None
        self.cache = {}

    @property
    def github_client(self):
        """Lazy-load GitHub client."""
        if self._github_client is None:
            self._github_client = GitHubClient()
        return self._github_client

    @property
    def bitbucket_client(self):
        """Lazy-load Bitbucket client."""
        if self._bitbucket_client is None:
            self._bitbucket_client = BitbucketClient()
        return self._bitbucket_client

    def get_repo_languages(
        self, platform: str, owner_or_project: str, repo_name_or_slug: str
    ) -> Dict[str, int]:
        """Get languages for a repository (GitHub or Bitbucket)."""
        if platform.lower() == "github":
            return self._get_github_languages(owner_or_project, repo_name_or_slug)
        return self._get_bitbucket_languages(owner_or_project, repo_name_or_slug)

    def get_developer_languages(
        self, repositories: List[Tuple[str, str, str]]
    ) -> Dict[str, int]:
        """Aggregate languages across all developer repositories."""
        developer_languages = {}
        for platform, owner_or_project, repo_name_or_slug in repositories:
            try:
                repo_languages = self.get_repo_languages(
                    platform, owner_or_project, repo_name_or_slug
                )
                self._merge_languages(developer_languages, repo_languages, platform)
            except Exception as e:
                logger.debug(
                    f"Error detecting languages for {platform} "
                    f"{owner_or_project}/{repo_name_or_slug}: {e}"
                )
        return developer_languages

    def _get_github_languages(self, owner: str, repo: str) -> Dict[str, int]:
        """Fetch languages from GitHub API (uses linguist)."""
        cache_key = f"github:{owner}/{repo}"
        if cache_key in self.cache:
            return self.cache[cache_key]

        try:
            languages = self.github_client._request(
                "GET", f"/repos/{owner}/{repo}/languages"
            )
            if languages:
                self.cache[cache_key] = languages
                return languages
        except Exception as e:
            logger.debug(f"Could not fetch GitHub languages for {owner}/{repo}: {e}")

        return {}

    def _get_bitbucket_languages(
        self, project_key: str, repo_slug: str
    ) -> Dict[str, int]:
        """Detect languages from Bitbucket repository file tree."""
        cache_key = f"bitbucket:{project_key}/{repo_slug}"
        if cache_key in self.cache:
            return self.cache[cache_key]

        languages = {}
        try:
            browse_data = self.bitbucket_client._request(
                "GET",
                f"/projects/{project_key}/repos/{repo_slug}/browse",
                params={"limit": 100},
            )
            if browse_data:
                self._count_file_extensions(browse_data, languages)
            self.cache[cache_key] = languages
        except Exception as e:
            logger.debug(
                f"Could not fetch Bitbucket files for {project_key}/{repo_slug}: {e}"
            )

        return languages

    def _count_file_extensions(self, node: Dict, languages: Dict) -> None:
        """Count file extensions in Bitbucket file tree node."""
        if not node:
            return

        for child in node.get("children", {}).get("values", []):
            if child.get("type") == "FILE":
                self._increment_language_count(child, languages)

    def _increment_language_count(self, file_node: Dict, languages: Dict) -> None:
        """Increment language count for a file based on extension."""
        filename = file_node.get("path", {}).get("name", "")
        if "." not in filename:
            return

        extension = filename.rsplit(".", 1)[-1].lower()
        language = EXTENSION_TO_LANGUAGE.get(extension)
        if language:
            languages[language] = languages.get(language, 0) + 1

    def _merge_languages(
        self, target: Dict[str, int], source: Dict[str, int], platform: str
    ) -> None:
        """Merge source languages into target, normalizing counts by platform."""
        for language, count in source.items():
            normalized = self._normalize_count(count, platform)
            target[language] = target.get(language, 0) + normalized

    def _normalize_count(self, count: int, platform: str) -> int:
        """Normalize language count based on platform metric."""
        if platform.lower() == "github":
            # GitHub: bytes -> approximate file count
            return max(1, count // BITBUCKET_LANGUAGE_DIVISOR)
        # Bitbucket: file count direct
        return max(1, count)
