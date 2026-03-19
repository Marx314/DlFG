"""Retry logic with exponential backoff and token rotation for API resilience."""

import logging
import time
import requests
from typing import Callable, Any, List, Optional
import random

logger = logging.getLogger(__name__)


class RetryConfig:
    """Configuration for retry behavior."""

    def __init__(
        self,
        max_retries: int = 5,
        initial_backoff: float = 1.0,
        max_backoff: float = 300.0,
        exponential_base: float = 2.0,
        jitter: bool = True,
    ):
        """
        Initialize retry configuration.

        Args:
            max_retries: Maximum number of retry attempts
            initial_backoff: Initial backoff time in seconds
            max_backoff: Maximum backoff time in seconds
            exponential_base: Multiplier for exponential backoff
            jitter: Whether to add random jitter to backoff
        """
        self.max_retries = max_retries
        self.initial_backoff = initial_backoff
        self.max_backoff = max_backoff
        self.exponential_base = exponential_base
        self.jitter = jitter

    def get_backoff_time(self, attempt: int) -> float:
        """
        Calculate backoff time for a given attempt.

        Args:
            attempt: Attempt number (0-indexed)

        Returns:
            Backoff time in seconds
        """
        backoff = min(self.initial_backoff * (self.exponential_base ** attempt), self.max_backoff)

        if self.jitter:
            # Add random jitter (±10%)
            jitter_amount = backoff * 0.1
            backoff += random.uniform(-jitter_amount, jitter_amount)

        return max(backoff, 0)  # Ensure non-negative


class TokenRotator:
    """Manages rotation through multiple API tokens."""

    def __init__(self, tokens: List[str]):
        """
        Initialize token rotator.

        Args:
            tokens: List of API tokens
        """
        self.tokens = [t for t in tokens if t]  # Filter out empty tokens
        self.current_index = 0
        self.rate_limited_until = {}  # token -> time until we can use it

    def get_current_token(self) -> Optional[str]:
        """Get current token."""
        if not self.tokens:
            return None
        return self.tokens[self.current_index]

    def mark_rate_limited(self, retry_after: int = 3600) -> None:
        """
        Mark current token as rate limited.

        Args:
            retry_after: Seconds until token can be reused
        """
        if not self.tokens:
            return

        token = self.get_current_token()
        self.rate_limited_until[token] = time.time() + retry_after
        logger.warning(f"Token rate limited, waiting {retry_after}s before retry")
        self.rotate()

    def rotate(self) -> None:
        """Rotate to next token."""
        if not self.tokens:
            return

        self.current_index = (self.current_index + 1) % len(self.tokens)
        token = self.get_current_token()

        # Check if new token is also rate limited
        if token in self.rate_limited_until:
            wait_time = self.rate_limited_until[token] - time.time()
            if wait_time > 0:
                logger.warning(f"Next token also rate limited, waiting {wait_time:.0f}s")
                time.sleep(min(wait_time, 5))  # Wait up to 5 seconds
            else:
                del self.rate_limited_until[token]

        logger.info(f"Rotated to token {self.current_index + 1}/{len(self.tokens)}")

    def has_available_tokens(self) -> bool:
        """Check if any tokens are available."""
        return len(self.tokens) > 0


class APIRetryHandler:
    """Handles retries for API calls with exponential backoff and token rotation."""

    def __init__(
        self,
        retry_config: Optional[RetryConfig] = None,
        tokens: Optional[List[str]] = None,
    ):
        """
        Initialize API retry handler.

        Args:
            retry_config: Retry configuration
            tokens: List of API tokens for rotation
        """
        self.retry_config = retry_config or RetryConfig()
        self.token_rotator = TokenRotator(tokens or [])
        self.attempt_stats = {
            "total_attempts": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "token_rotations": 0,
        }

    def should_retry(self, error: Exception, attempt: int) -> bool:
        """
        Determine if a request should be retried.

        Args:
            error: The exception that occurred
            attempt: Current attempt number

        Returns:
            True if should retry, False otherwise
        """
        if attempt >= self.retry_config.max_retries:
            return False

        # Retry on network errors
        if isinstance(error, (requests.ConnectionError, requests.Timeout)):
            logger.warning(f"Network error (attempt {attempt + 1}): {error}")
            return True

        # Retry on specific HTTP status codes
        if isinstance(error, requests.exceptions.HTTPError):
            status_code = error.response.status_code if hasattr(error, "response") else None

            # Rate limit (429)
            if status_code == 429:
                # Check for X-RateLimit-Reset header (GitHub uses this)
                reset_timestamp = error.response.headers.get("X-RateLimit-Reset")
                if reset_timestamp:
                    try:
                        reset_time = int(reset_timestamp)
                        wait_seconds = max(0, reset_time - time.time())
                        logger.warning(
                            f"Rate limited (429), sleeping until reset ({wait_seconds:.0f}s)"
                        )
                        self.token_rotator.mark_rate_limited(int(wait_seconds) + 1)
                    except (ValueError, AttributeError):
                        pass
                else:
                    retry_after = int(error.response.headers.get("Retry-After", 60))
                    logger.warning(f"Rate limited (429), retry after {retry_after}s")
                    self.token_rotator.mark_rate_limited(retry_after)
                return True

            # Server errors (5xx)
            if status_code and 500 <= status_code < 600:
                logger.warning(f"Server error ({status_code}), will retry")
                return True

            # Timeout-like responses
            if status_code in [408, 504]:
                logger.warning(f"Timeout-like response ({status_code}), will retry")
                return True

        # Don't retry on client errors (4xx except those above)
        return False

    def execute_with_retry(
        self,
        func: Callable,
        *args,
        update_token_callback: Optional[Callable] = None,
        **kwargs,
    ) -> Any:
        """
        Execute a function with automatic retries.

        Args:
            func: Function to execute
            args: Positional arguments for function
            update_token_callback: Callback to update token in the function
            **kwargs: Keyword arguments for function

        Returns:
            Function result
        """
        attempt = 0
        last_error = None

        while attempt <= self.retry_config.max_retries:
            try:
                self.attempt_stats["total_attempts"] += 1

                # Update token if callback provided and tokens available
                if update_token_callback and self.token_rotator.has_available_tokens():
                    token = self.token_rotator.get_current_token()
                    if token:
                        update_token_callback(token)

                result = func(*args, **kwargs)
                self.attempt_stats["successful_requests"] += 1
                return result

            except Exception as error:
                last_error = error
                logger.debug(f"Attempt {attempt + 1} failed: {error}")

                if not self.should_retry(error, attempt):
                    self.attempt_stats["failed_requests"] += 1
                    logger.error(f"Request failed permanently: {error}")
                    raise

                # Calculate backoff time
                backoff_time = self.retry_config.get_backoff_time(attempt)
                attempt += 1

                logger.info(
                    f"Retrying in {backoff_time:.1f}s (attempt {attempt}/{self.retry_config.max_retries})"
                )
                time.sleep(backoff_time)

        # All retries exhausted
        self.attempt_stats["failed_requests"] += 1
        logger.error(f"All {self.retry_config.max_retries} retries exhausted")
        raise last_error

    def get_stats(self) -> dict:
        """Get retry statistics."""
        return dict(self.attempt_stats)
