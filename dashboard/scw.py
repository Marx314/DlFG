
import logging
import re
from typing import List, Dict, Optional
from datetime import date, datetime
from dateutil.relativedelta import relativedelta
from retry_handler import APIRetryHandler
from config import SCW_API_BASE, BATCH_TAG_PATTERN

logger = logging.getLogger(__name__)


class SCWClient:

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = SCW_API_BASE
        self.retry_handler = APIRetryHandler()

        self.headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json',
        }

    def _request(self, method: str, endpoint: str, **kwargs) -> Dict:
        import requests

        url = f"{self.base_url}{endpoint}"

        def make_request():
            headers = self.headers.copy()
            if 'headers' in kwargs:
                headers.update(kwargs['headers'])
                del kwargs['headers']

            resp = requests.request(method, url, headers=headers, timeout=30, **kwargs)
            resp.raise_for_status()
            return resp.json()

        return self.retry_handler.execute_with_retry(make_request)

    def get_all_tags(self) -> List[Dict]:
        try:
            logger.debug("Fetching all tags from SCW...")
            response = self._request('GET', '/tags')
            tags = response.get('items', response.get('data', response if isinstance(response, list) else []))
            logger.info(f"Fetched {len(tags)} tags from SCW")
            return tags
        except Exception as e:
            logger.error(f"Failed to fetch tags from SCW: {e}")
            raise

    def get_users_by_tag(self, tag_id: str) -> List[Dict]:
        try:
            logger.debug(f"Fetching users for tag {tag_id}...")
            response = self._request('GET', f'/users?tag={tag_id}')
            users = response.get('items', response.get('data', response if isinstance(response, list) else []))
            logger.debug(f"Tag {tag_id}: {len(users)} users")
            return users
        except Exception as e:
            logger.error(f"Failed to fetch users for tag {tag_id}: {e}")
            raise

    @staticmethod
    def is_valid_batch_tag(tag_name: str) -> bool:
        return bool(re.match(BATCH_TAG_PATTERN, tag_name))

    @staticmethod
    def parse_batch_tag(tag_name: str) -> Optional[tuple]:
        if not SCWClient.is_valid_batch_tag(tag_name):
            return None

        parts = tag_name.split('-')
        return int(parts[0]), int(parts[1])

    @staticmethod
    def calculate_due_date(tag_name: str) -> date:
        parsed = SCWClient.parse_batch_tag(tag_name)
        if not parsed:
            raise ValueError(f"Invalid batch tag format: {tag_name}")

        year, month = parsed
        batch_date = date(year, month, 1)
        due_date = batch_date + relativedelta(months=2)
        due_date = due_date + relativedelta(day=31)

        return due_date

    @staticmethod
    def get_batch_invited_date(tag_name: str) -> date:
        parsed = SCWClient.parse_batch_tag(tag_name)
        if not parsed:
            raise ValueError(f"Invalid batch tag format: {tag_name}")

        year, month = parsed
        return date(year, month, 1)
