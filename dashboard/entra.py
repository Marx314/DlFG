
import logging
import time
import requests
from typing import List, Dict, Optional, Tuple
from datetime import datetime
from retry_handler import APIRetryHandler, RetryConfig
from config import (
    AZURE_TENANT_ID,
    AZURE_CLIENT_ID,
    AZURE_CLIENT_SECRET,
    MICROSOFT_GRAPH_API_BASE,
    GRAPH_PAGE_SIZE,
)

logger = logging.getLogger(__name__)


class EntraClient:

    _token_cache = {
        'token': None,
        'expires_at': 0,
    }

    def __init__(self, tenant_id: str, client_id: str, client_secret: str):
        self.tenant_id = tenant_id
        self.client_id = client_id
        self.client_secret = client_secret
        self.session = requests.Session()
        self.retry_handler = APIRetryHandler()

        self._refresh_token_if_needed()

    def _get_oauth_token(self) -> str:
        url = f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token"
        payload = {
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'scope': 'https://graph.microsoft.com/.default',
            'grant_type': 'client_credentials',
        }

        def fetch_token():
            resp = requests.post(url, data=payload, timeout=10)
            resp.raise_for_status()
            return resp.json()

        try:
            response = self.retry_handler.execute_with_retry(fetch_token)
            token = response['access_token']
            expires_in = response.get('expires_in', 3600)
            self._token_cache['token'] = token
            self._token_cache['expires_at'] = time.time() + expires_in - 60
            logger.debug("OAuth token obtained")
            return token
        except Exception as e:
            logger.error(f"Failed to obtain OAuth token: {e}")
            raise

    def _refresh_token_if_needed(self):
        if time.time() >= self._token_cache.get('expires_at', 0):
            token = self._get_oauth_token()
            self.session.headers['Authorization'] = f'Bearer {token}'

    def _request(self, method: str, endpoint: str, **kwargs) -> Dict:
        self._refresh_token_if_needed()

        url = f"{MICROSOFT_GRAPH_API_BASE}{endpoint}"

        def make_request():
            resp = self.session.request(method, url, timeout=30, **kwargs)
            resp.raise_for_status()
            return resp.json()

        return self.retry_handler.execute_with_retry(make_request)

    def get_all_users(self) -> List[Dict]:
        users = []
        next_link = None
        page = 0
        try:
            while True:
                page += 1
                data = self._fetch_page(next_link, page)
                users.extend(data.get('value', []))
                logger.debug(f"Page {page}: {len(data.get('value', []))} users (total: {len(users)})")
                next_link = data.get('@odata.nextLink')
                if not next_link:
                    break
            logger.info(f"Fetched total of {len(users)} users from Entra ID")
            return users
        except Exception as e:
            logger.error(f"Pagination failed after {len(users)} users: {e}")
            raise RuntimeError(f"Failed to fetch all users from Entra ID (got {len(users)} before failure): {e}")

    def _fetch_page(self, next_link: Optional[str], page: int) -> Dict:
        logger.debug(f"Fetching users page {page}...")
        if next_link:
            resp = self.session.get(next_link, timeout=30, headers={'Authorization': self.session.headers['Authorization']})
            resp.raise_for_status()
            return resp.json()
        params = {'$select': 'id,mail,displayName,accountEnabled,offboardedDateTime', '$top': GRAPH_PAGE_SIZE}
        return self._request('GET', '/users', params=params)

    def walk_manager_chain(self, user_id: str) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
        chain = [None, None, None, None]
        level = 0
        current_user_id = user_id
        try:
            while level < 4:
                manager = self._fetch_manager(current_user_id)
                if not manager or not manager.get('mail'):
                    break
                chain[level] = manager.get('mail')
                logger.debug(f"Level {level}: {manager.get('mail')}")
                current_user_id = manager.get('id')
                level += 1
        except Exception as e:
            logger.debug(f"Error walking manager chain for user {user_id}: {e}")
        return tuple(chain)

    def _fetch_manager(self, user_id: str) -> Optional[Dict]:
        params = {'$select': 'id,mail,displayName', '$expand': 'manager($select=id,mail,displayName)'}
        resp = self._request('GET', f"/users/{user_id}", params=params)
        return resp.get('manager')

    def get_user_by_id(self, user_id: str) -> Optional[Dict]:
        try:
            params = {
                '$select': 'id,mail,displayName,accountEnabled,offboardedDateTime',
            }
            return self._request('GET', f'/users/{user_id}', params=params)
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                return None
            raise
