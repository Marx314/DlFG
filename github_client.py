"""GitHub API client for fetching developer and commit data."""

import logging
import requests
from typing import List, Dict, Optional
from config import (
    GITHUB_API_BASE,
    GITHUB_TOKEN,
    GITHUB_TOKENS,
    SINCE_DATE,
    EXCLUDE_ARCHIVED,
    EXCLUDE_FORKS,
    MAX_RETRIES,
    INITIAL_BACKOFF,
    MAX_BACKOFF,
    EXPONENTIAL_BASE,
    GITHUB_CUSTOM_PROPERTIES,
    GITHUB_PAGINATION_SIZE,
)
from excluded_repos_config import ExcludedRepoFilter
from retry_handler import APIRetryHandler, RetryConfig
from commit_cache import CommitCache

logger = logging.getLogger(__name__)


class GitHubClient:
    """Client for interacting with GitHub API."""

    def __init__(
        self,
        token: Optional[str] = None,
        tokens: Optional[List[str]] = None,
        commit_cache: Optional[CommitCache] = None,
    ):
        """
        Initialize GitHub client.

        Args:
            token: Primary GitHub API token
            tokens: List of GitHub tokens for rate limit rotation
            commit_cache: Optional CommitCache instance for caching commits
        """
        self.tokens = tokens or GITHUB_TOKENS or (
            [token] if token else ([GITHUB_TOKEN] if GITHUB_TOKEN else [])
        )
        self.token = self.tokens[0] if self.tokens else None

        self.base_url = GITHUB_API_BASE
        self.headers = {
            "Authorization": f"token {self.token}" if self.token else "",
            "Accept": "application/vnd.github.v3+json",
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        self.excluded_filter = ExcludedRepoFilter()
        self.commit_cache = commit_cache

        # Initialize retry handler with token rotation
        retry_config = RetryConfig(
            max_retries=MAX_RETRIES,
            initial_backoff=INITIAL_BACKOFF,
            max_backoff=MAX_BACKOFF,
            exponential_base=EXPONENTIAL_BASE,
        )
        self.retry_handler = APIRetryHandler(
            retry_config=retry_config, tokens=self.tokens
        )
        logger.info(f"GitHub client initialized with {len(self.tokens)} tokens")

    def _update_token(self, token: str) -> None:
        """Update the current token in headers."""
        self.token = token
        self.headers["Authorization"] = f"token {token}"
        self.session.headers.update(self.headers)

    def _paginate(
        self, endpoint: str, per_page: int = GITHUB_PAGINATION_SIZE, **params
    ) -> List[Dict]:
        """
        Generic paginated request using GitHub's page-based pagination.

        Args:
            endpoint: API endpoint path
            per_page: Items per page (default: GITHUB_PAGINATION_SIZE)
            **params: Additional query parameters

        Returns:
            List of all items across paginated responses
        """
        items = []
        page = 1

        while True:
            request_params = {**params, "page": page, "per_page": per_page}
            data = self._request("GET", endpoint, params=request_params)

            if not data:
                break

            items.extend(data)
            page += 1

        return items

    def _request(
        self, method: str, endpoint: str, **kwargs
    ) -> Dict:
        """
        Make authenticated request to GitHub API with automatic retry.

        Args:
            method: HTTP method
            endpoint: API endpoint path
            **kwargs: Additional arguments to pass to requests

        Returns:
            Response JSON as dictionary
        """
        url = f"{self.base_url}{endpoint}"

        def _make_request():
            response = self.session.request(method, url, **kwargs)
            response.raise_for_status()
            return response.json()

        return self.retry_handler.execute_with_retry(
            _make_request,
            update_token_callback=self._update_token,
        )

    def get_user_repos(self, username: str) -> List[Dict]:
        """
        Get all repositories for a user.

        Args:
            username: GitHub username

        Returns:
            List of repository dictionaries
        """
        return self._paginate(f"/users/{username}/repos", type="all")

    def get_org_repos(self, org: str) -> List[Dict]:
        """
        Get all repositories for an organization.

        Args:
            org: GitHub organization name

        Returns:
            List of repository dictionaries
        """
        return self._paginate(f"/orgs/{org}/repos", type="all")

    def get_repo_properties(self, owner: str, repo: str) -> Dict:
        """
        Get custom properties for a repository (GitHub Enterprise feature).

        Only fetches properties specified in GITHUB_CUSTOM_PROPERTIES config.
        Skips if no properties configured.

        Args:
            owner: Repository owner
            repo: Repository name

        Returns:
            Dictionary of requested custom properties
        """
        if not GITHUB_CUSTOM_PROPERTIES:
            return {}  # Skip if no properties configured

        try:
            data = self._request("GET", f"/repos/{owner}/{repo}/properties/values")
            if not data or not isinstance(data, dict):
                return {}

            # Filter to only requested properties
            filtered_props = {}
            for prop_name in GITHUB_CUSTOM_PROPERTIES:
                if prop_name in data:
                    filtered_props[prop_name] = data[prop_name]

            return filtered_props

        except Exception as e:
            logger.debug(f"Could not fetch properties for {owner}/{repo}: {e}")
            return {}

    def get_repo_commits(self, owner: str, repo: str) -> List[Dict]:
        """
        Get commits for a repository since SINCE_DATE.

        Args:
            owner: Repository owner
            repo: Repository name

        Returns:
            List of commit dictionaries
        """
        # Check cache first
        if self.commit_cache:
            cached_commits = self.commit_cache.get_cached_commits("github", owner, repo)
            if cached_commits is not None:
                logger.info(f"Using cached commits for {owner}/{repo} ({len(cached_commits)} commits)")
                return cached_commits

        # Fetch from API if not cached
        commits = self._paginate(f"/repos/{owner}/{repo}/commits", since=SINCE_DATE)

        # Store in cache
        if self.commit_cache and commits:
            self.commit_cache.cache_commits("github", owner, repo, commits)
            logger.debug(f"Cached {len(commits)} commits for {owner}/{repo}")

        return commits

    def filter_repos(self, repos: List[Dict]) -> List[Dict]:
        """
        Filter repositories based on configuration.

        Args:
            repos: List of repository dictionaries

        Returns:
            Filtered list of repositories
        """
        filtered = repos

        if EXCLUDE_ARCHIVED:
            filtered = [r for r in filtered if not r.get("archived", False)]

        if EXCLUDE_FORKS:
            filtered = [r for r in filtered if not r.get("fork", False)]

        # Exclude repositories
        filtered = [
            r for r in filtered
            if not self.excluded_filter.is_excluded_repo("github", r["owner"]["login"], r["name"])
        ]

        return filtered

    def get_authenticated_user(self) -> Dict:
        """
        Get authenticated user information.

        Returns:
            User dictionary
        """
        return self._request("GET", "/user")
