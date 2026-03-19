"""Azure/Microsoft Graph API client for employee and manager data."""

import logging
import requests
from typing import List, Dict, Optional
from config import (
    AZURE_TENANT_ID,
    AZURE_CLIENT_ID,
    AZURE_CLIENT_SECRET,
    AZURE_GRAPH_ENDPOINT,
)

logger = logging.getLogger(__name__)


class AzureGraphClient:
    """Client for interacting with Microsoft Graph API."""

    def __init__(
        self,
        tenant_id: Optional[str] = None,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
    ):
        """
        Initialize Azure Graph client.

        Args:
            tenant_id: Azure tenant ID (uses config if not provided)
            client_id: Azure app client ID (uses config if not provided)
            client_secret: Azure app client secret (uses config if not provided)
        """
        self.tenant_id = tenant_id or AZURE_TENANT_ID
        self.client_id = client_id or AZURE_CLIENT_ID
        self.client_secret = client_secret or AZURE_CLIENT_SECRET
        self.graph_endpoint = AZURE_GRAPH_ENDPOINT

        self.access_token = None
        self.session = requests.Session()

        if self.client_id and self.client_secret and self.tenant_id:
            self._authenticate()
        else:
            logger.warning("Azure credentials not fully configured. Some features may not work.")

    def _authenticate(self) -> None:
        """Authenticate and get access token from Azure."""
        auth_url = f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token"

        payload = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "scope": f"{self.graph_endpoint}/.default",
        }

        try:
            response = requests.post(auth_url, data=payload)
            response.raise_for_status()
            self.access_token = response.json()["access_token"]
            logger.info("Successfully authenticated with Azure")
        except Exception as e:
            logger.error(f"Failed to authenticate with Azure: {e}")
            raise

    def _request(self, method: str, endpoint: str, **kwargs) -> Dict:
        """
        Make authenticated request to Microsoft Graph API.

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint path
            **kwargs: Additional arguments to pass to requests

        Returns:
            Response JSON as dictionary
        """
        if not self.access_token:
            raise RuntimeError("Not authenticated with Azure. Call _authenticate() first.")

        url = f"{self.graph_endpoint}{endpoint}"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

        try:
            response = self.session.request(method, url, headers=headers, **kwargs)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Graph API error: {e}")
            raise

    def get_all_users(self) -> List[Dict]:
        """
        Get all users from Azure AD.

        Returns:
            List of user dictionaries
        """
        users = []
        next_link = "/users?$select=id,displayName,userPrincipalName,mail,jobTitle,department,manager"

        while next_link:
            data = self._request("GET", next_link)
            users.extend(data.get("value", []))

            # Get next page if available
            next_link = data.get("@odata.nextLink", "").replace(self.graph_endpoint, "")

        logger.info(f"Retrieved {len(users)} users from Azure AD")
        return users

    def get_user_manager(self, user_id: str) -> Optional[Dict]:
        """
        Get direct manager for a user.

        Args:
            user_id: User ID (or UPN)

        Returns:
            Manager information dictionary or None
        """
        try:
            data = self._request("GET", f"/users/{user_id}/manager")
            if data:
                return {
                    "id": data.get("id"),
                    "displayName": data.get("displayName"),
                    "userPrincipalName": data.get("userPrincipalName"),
                    "mail": data.get("mail"),
                }
            return None
        except Exception as e:
            logger.debug(f"Could not fetch manager for {user_id}: {e}")
            return None

    def get_user_chain_of_command(self, user_id: str, max_depth: int = 5) -> List[Dict]:
        """
        Get full chain of command (manager and above) for a user.

        Args:
            user_id: User ID (or UPN)
            max_depth: Maximum levels to traverse up

        Returns:
            List of managers in hierarchy (direct manager first)
        """
        managers = []
        current_id = user_id
        depth = 0

        while depth < max_depth:
            manager = self.get_user_manager(current_id)
            if not manager:
                break

            managers.append(manager)
            current_id = manager.get("id")
            depth += 1

        return managers

    def get_user_by_email(self, email: str) -> Optional[Dict]:
        """
        Get user information by email.

        Args:
            email: User email address

        Returns:
            User dictionary or None
        """
        try:
            data = self._request("GET", f"/users/{email}")
            return data
        except Exception as e:
            logger.debug(f"Could not fetch user {email}: {e}")
            return None

    def search_users_by_mail(self, email_pattern: str) -> List[Dict]:
        """
        Search users by email pattern.

        Args:
            email_pattern: Email pattern (supports partial match)

        Returns:
            List of matching users
        """
        try:
            filter_str = f"startswith(userPrincipalName,'{email_pattern}') or startswith(mail,'{email_pattern}')"
            data = self._request(
                "GET",
                f"/users?$filter={filter_str}&$select=id,displayName,userPrincipalName,mail,jobTitle,department",
            )
            return data.get("value", [])
        except Exception as e:
            logger.warning(f"Search failed for {email_pattern}: {e}")
            return []
