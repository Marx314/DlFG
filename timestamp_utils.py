"""Centralized timestamp conversion utilities."""

from datetime import datetime
from typing import Optional


class TimestampConverter:
    """Converts timestamps between milliseconds and ISO format."""

    @staticmethod
    def to_iso_format(milliseconds: int) -> str:
        """
        Convert milliseconds timestamp to ISO format string.

        Args:
            milliseconds: Unix timestamp in milliseconds

        Returns:
            ISO format string (YYYY-MM-DDTHH:MM:SS)

        Raises:
            ValueError: If timestamp is invalid
        """
        try:
            return datetime.fromtimestamp(milliseconds / 1000).isoformat()
        except (ValueError, OSError) as e:
            raise ValueError(f"Invalid timestamp {milliseconds}: {e}")

    @staticmethod
    def from_iso_format(iso_string: str) -> int:
        """
        Convert ISO format string to milliseconds timestamp.

        Args:
            iso_string: ISO format string (handles Z for UTC)

        Returns:
            Unix timestamp in milliseconds

        Raises:
            ValueError: If string is not valid ISO format
        """
        try:
            normalized = iso_string.replace("Z", "+00:00")
            dt = datetime.fromisoformat(normalized)
            return int(dt.timestamp() * 1000)
        except ValueError as e:
            raise ValueError(f"Invalid ISO format '{iso_string}': {e}")

    @staticmethod
    def get_month_string(iso_date: str) -> str:
        """
        Extract YYYY-MM from ISO date string.

        Args:
            iso_date: ISO format date string

        Returns:
            Month string in YYYY-MM format, or current month if invalid

        Examples:
            >>> TimestampConverter.get_month_string("2026-03-15T10:30:00")
            '2026-03'
        """
        if iso_date and len(iso_date) >= 7:
            return iso_date[:7]
        return datetime.utcnow().strftime("%Y-%m")
