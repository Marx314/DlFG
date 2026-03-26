"""Bitbucket Server API client for fetching developer and commit data."""

import logging
import requests
from typing import List, Dict, Optional
from requests.auth import HTTPBasicAuth
from config import (
    BITBUCKET_API_BASE,
    BITBUCKET_URL,
    BITBUCKET_USER,
    BITBUCKET_PASS,
    BITBUCKET_PASSES,
    SINCE_DATE,
    MAX_RETRIES,
    INITIAL_BACKOFF,
    MAX_BACKOFF,
    EXPONENTIAL_BASE,
    BITBUCKET_PAGINATION_SIZE,
    BITBUCKET_TIMESTAMP_DIVISOR,
)
from excluded_repos_config import ExcludedRepoFilter
from retry_handler import APIRetryHandler, RetryConfig
from timestamp_utils import TimestampConverter
from commit_cache import CommitCache

logger = logging.getLogger(__name__)


class BitbucketClient:
    """Client for interacting with Bitbucket Server API v1.0."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        passwords: Optional[List[str]] = None,
        commit_cache: Optional[CommitCache] = None,
    ):
        """
        Initialize Bitbucket Server client.

        Args:
            base_url: Bitbucket Server instance URL
            username: Bitbucket username
            password: Bitbucket password/token
            passwords: List of passwords/tokens for rate limit rotation
            commit_cache: Optional CommitCache instance for caching commits
        """
        self.base_url = base_url or BITBUCKET_API_BASE
        self.bitbucket_url = BITBUCKET_URL
        self.username = username or BITBUCKET_USER

        # Use provided passwords, or fall back to environment
        self.passwords = passwords or BITBUCKET_PASSES or (
            [password] if password else ([BITBUCKET_PASS] if BITBUCKET_PASS else [])
        )
        self.password = self.passwords[0] if self.passwords else None

        self.auth = (
            HTTPBasicAuth(self.username, self.password)
            if self.username and self.password
            else None
        )
        self.session = requests.Session()
        if self.auth:
            self.session.auth = self.auth
        self.session.headers.update({"Accept": "application/json"})

        self.excluded_filter = ExcludedRepoFilter()
        self.commit_cache = commit_cache

        # Initialize retry handler with password rotation
        retry_config = RetryConfig(
            max_retries=MAX_RETRIES,
            initial_backoff=INITIAL_BACKOFF,
            max_backoff=MAX_BACKOFF,
            exponential_base=EXPONENTIAL_BASE,
        )
        self.retry_handler = APIRetryHandler(
            retry_config=retry_config, tokens=self.passwords
        )
        logger.info(f"Bitbucket Server client initialized with {len(self.passwords)} credentials")

    def _update_password(self, password: str) -> None:
        """Update the current password in auth."""
        self.password = password
        self.auth = (
            HTTPBasicAuth(self.username, password)
            if self.username and password
            else None
        )
        self.session.auth = self.auth

    def _paginate_bitbucket(
        self, endpoint: str, limit: int = BITBUCKET_PAGINATION_SIZE, **params
    ) -> List[Dict]:
        """
        Generic paginated request using Bitbucket's offset-based pagination.

        Args:
            endpoint: API endpoint path
            limit: Items per page (default: BITBUCKET_PAGINATION_SIZE)
            **params: Additional query parameters

        Returns:
            List of all items across paginated responses
        """
        items = []
        start = 0

        while True:
            request_params = {**params, "start": start, "limit": limit}
            data = self._request("GET", endpoint, params=request_params)

            if data is None or not data.get("values"):
                break

            items.extend(data["values"])

            if data.get("isLastPage", True):
                break

            start += limit

        return items

    def _request(self, method: str, endpoint: str, **kwargs) -> Dict:
        """
        Make authenticated request to Bitbucket Server API with automatic retry.

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint path
            **kwargs: Additional arguments to pass to requests

        Returns:
            Response JSON as dictionary
        """
        url = f"{self.base_url}{endpoint}"

        def _make_request():
            response = self.session.request(method, url, **kwargs)
            if response.status_code == 404:
                return None
            response.raise_for_status()
            return response.json()

        return self.retry_handler.execute_with_retry(
            _make_request,
            update_token_callback=self._update_password,
        )

    def get_all_projects(self) -> List[Dict]:
        """
        Get all projects from Bitbucket Server.

        Returns:
            List of project dictionaries
        """
        return self._paginate_bitbucket("/projects")

    def get_project_repos(self, project_key: str) -> List[Dict]:
        """
        Get all repositories in a project.

        Args:
            project_key: Bitbucket Server project key

        Returns:
            List of repository dictionaries
        """
        return self._paginate_bitbucket(f"/projects/{project_key}/repos")

    def get_repo_commits(self, project_key: str, repo_slug: str) -> List[Dict]:
        """
        Get commits for a repository since SINCE_DATE.

        Args:
            project_key: Bitbucket Server project key
            repo_slug: Repository slug

        Returns:
            List of commit dictionaries
        """
        # Check cache first
        if self.commit_cache:
            cached_commits = self.commit_cache.get_cached_commits("bitbucket", project_key, repo_slug)
            if cached_commits is not None:
                logger.info(f"Using cached commits for {project_key}/{repo_slug} ({len(cached_commits)} commits)")
                return cached_commits

        commits = []
        start = 0
        limit = BITBUCKET_PAGINATION_SIZE

        # Convert SINCE_DATE to milliseconds for filtering
        since_timestamp = TimestampConverter.from_iso_format(SINCE_DATE)

        while True:
            data = self._request(
                "GET",
                f"/projects/{project_key}/repos/{repo_slug}/commits",
                params={"start": start, "limit": limit},
            )

            if data is None or not data.get("values"):
                break

            # Filter commits by date
            filtered_commits = [
                c
                for c in data["values"]
                if c.get("authorTimestamp", 0) >= since_timestamp
            ]
            commits.extend(filtered_commits)

            # Stop if we've gone past SINCE_DATE
            if filtered_commits and len(filtered_commits) < len(data["values"]):
                break

            if data.get("isLastPage", True):
                break

            start += limit

        # Store in cache
        if self.commit_cache and commits:
            self.commit_cache.cache_commits("bitbucket", project_key, repo_slug, commits)
            logger.debug(f"Cached {len(commits)} commits for {project_key}/{repo_slug}")

        return commits

    def filter_repos(self, repos: List[Dict]) -> List[Dict]:
        """
        Filter repositories based on configuration.

        Args:
            repos: List of repository dictionaries

        Returns:
            Filtered list of repositories
        """
        filtered = []
        for repo in repos:
            project_key = repo.get("project", {}).get("key", "")
            repo_slug = repo.get("slug", "")

            # Exclude archived repos
            if repo.get("archived", False):
                continue

            # Exclude based on external config
            if self.excluded_filter.is_excluded_repo(
                "bitbucket", project_key, repo_slug
            ):
                continue

            filtered.append(repo)

        return filtered

    def get_authenticated_user(self) -> Dict:
        """
        Get authenticated user information.

        Returns:
            User dictionary
        """
        return self._request("GET", "/users/current")
