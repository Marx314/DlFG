"""Service account and bot detection and filtering."""

import logging
from typing import List
from fnmatch import fnmatch
from config import SERVICE_ACCOUNT_PATTERNS

logger = logging.getLogger(__name__)


class ServiceAccountFilter:
    """Identify and filter service accounts and bots."""

    def __init__(self, patterns: List[str] = None):
        """
        Initialize service account filter.

        Args:
            patterns: List of wildcard patterns to match service accounts
        """
        self.patterns = patterns or SERVICE_ACCOUNT_PATTERNS
        logger.info(f"Service account filter initialized with {len(self.patterns)} patterns")

    def is_service_account(self, developer_name: str, email: str = "") -> bool:
        """
        Check if a developer name or email matches service account patterns.

        Args:
            developer_name: Developer name to check
            email: Developer email to check

        Returns:
            True if matches service account pattern, False otherwise
        """
        name_lower = developer_name.lower()
        email_lower = (email or "").lower()

        for pattern in self.patterns:
            pattern_lower = pattern.lower()
            if fnmatch(name_lower, pattern_lower):
                logger.debug(
                    f"Identified service account: {developer_name} (pattern: {pattern})"
                )
                return True
            if email_lower and fnmatch(email_lower, pattern_lower):
                logger.debug(
                    f"Identified service account by email: {email} (pattern: {pattern})"
                )
                return True

        return False

    def filter_developers(self, developers: dict) -> dict:
        """
        Filter out service accounts from developer dictionary.

        Args:
            developers: Dictionary of developers

        Returns:
            Filtered dictionary excluding service accounts
        """
        filtered = {}
        service_count = 0

        for dev_name, dev_data in developers.items():
            email = dev_data.get("email", "")
            if not self.is_service_account(dev_name, email):
                filtered[dev_name] = dev_data
            else:
                service_count += 1

        return filtered
