
import logging
import time
import random
import requests
from typing import Callable, Any
from config import MAX_RETRIES, INITIAL_BACKOFF, MAX_BACKOFF, EXPONENTIAL_BASE

logger = logging.getLogger(__name__)


class RetryConfig:

    def __init__(
        self,
        max_retries: int = 3,
        initial_backoff: float = 1.0,
        max_backoff: float = 60.0,
        exponential_base: float = 2.0,
        jitter: bool = True,
    ):
        self.max_retries = max_retries
        self.initial_backoff = initial_backoff
        self.max_backoff = max_backoff
        self.exponential_base = exponential_base
        self.jitter = jitter

    def get_backoff_time(self, attempt: int) -> float:
        backoff = min(
            self.initial_backoff * (self.exponential_base ** attempt),
            self.max_backoff
        )

        if self.jitter:
            jitter_amount = backoff * 0.1
            backoff = backoff + random.uniform(-jitter_amount, jitter_amount)

        return max(0, backoff)


class APIRetryHandler:

    def __init__(self, config: RetryConfig = None):
        self.config = config or RetryConfig(
            max_retries=MAX_RETRIES,
            initial_backoff=INITIAL_BACKOFF,
            max_backoff=MAX_BACKOFF,
            exponential_base=EXPONENTIAL_BASE,
        )

    def should_retry(self, error: Exception, attempt: int) -> bool:
        if attempt >= self.config.max_retries:
            return False

        if isinstance(error, requests.exceptions.ConnectionError):
            return True
        if isinstance(error, requests.exceptions.Timeout):
            return True
        if isinstance(error, requests.exceptions.RequestException):
            if hasattr(error, 'response') and error.response is not None:
                status = error.response.status_code
                return status in (408, 429, 500, 502, 503, 504)
            return True

        return False

    def execute_with_retry(self, func: Callable[[], Any]) -> Any:
        last_error = None

        for attempt in range(self.config.max_retries):
            try:
                result = func()
                if attempt > 0:
                    logger.debug(f"Retry succeeded on attempt {attempt + 1}")
                return result

            except Exception as e:
                last_error = e

                if not self.should_retry(e, attempt):
                    logger.debug(f"Error not retryable, raising immediately: {type(e).__name__}")
                    raise

                if attempt < self.config.max_retries - 1:
                    backoff = self.config.get_backoff_time(attempt)
                    logger.debug(
                        f"Attempt {attempt + 1} failed ({type(e).__name__}), "
                        f"retrying in {backoff:.2f}s..."
                    )
                    time.sleep(backoff)
                else:
                    logger.debug(
                        f"All {self.config.max_retries} attempts exhausted. "
                        f"Last error: {type(e).__name__}: {e}"
                    )

        raise last_error
