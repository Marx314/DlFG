"""Delta processing for identifying new/gone developers and enriching with manager data."""

import logging
from typing import Dict, List, Tuple, Optional
from datetime import datetime, timedelta
from config import DAYS_INACTIVE
from azure_client import AzureGraphClient

logger = logging.getLogger(__name__)


class DeltaProcessor:
    """Process developer inventory against Azure AD for changes and enrichment."""

    def __init__(self, azure_client: Optional[AzureGraphClient] = None):
        """
        Initialize delta processor.

        Args:
            azure_client: AzureGraphClient instance
        """
        self.azure_client = azure_client or AzureGraphClient()
        self.azure_users = {}
        self.azure_users_by_email = {}
        self.manager_cache = {}
        self._load_azure_data()

    def _load_azure_data(self) -> None:
        """Load all users and managers from Azure."""
        try:
            users = self.azure_client.get_all_users()
            self.azure_users = {user.get("id"): user for user in users}
            self.azure_users_by_email = {user.get("mail", "").lower(): user for user in users}
            logger.info(f"Loaded {len(self.azure_users)} users from Azure AD")
        except Exception as e:
            logger.warning(f"Failed to load Azure data: {e}")

    def identify_new_developers(self, developers: Dict) -> List[str]:
        """
        Identify developers not in Azure AD (new/external).

        Args:
            developers: Dictionary of developers from inventory

        Returns:
            List of developer names that are new
        """
        new_devs = []

        for dev_name, dev_data in developers.items():
            email = dev_data.get("email", "").lower()
            # Check if developer exists in Azure by email
            if email and email not in self.azure_users_by_email:
                new_devs.append(dev_name)
                logger.debug(f"Identified new developer: {dev_name} ({email})")

        return new_devs

    def identify_gone_developers(
        self, developers: Dict, last_seen_threshold_days: int = DAYS_INACTIVE
    ) -> List[Tuple[str, str]]:
        """
        Identify developers who are in Azure but haven't committed recently.

        Args:
            developers: Dictionary of current developers from inventory
            last_seen_threshold_days: Days of inactivity to consider "gone"

        Returns:
            List of tuples (developer_name, last_seen_date)
        """
        gone_devs = []
        dev_emails = {dev_data.get("email", "").lower(): name for name, dev_data in developers.items()}

        threshold_date = (datetime.now() - timedelta(days=last_seen_threshold_days)).strftime("%Y-%m-%d")

        for user in self.azure_users.values():
            email = user.get("mail", "").lower()
            if not email:
                continue

            # If user is in Azure but NOT in current inventory, they might be "gone"
            if email not in dev_emails:
                logger.debug(f"Identified gone developer: {user.get('displayName')} ({email})")
                gone_devs.append((user.get("displayName", ""), threshold_date))

        return gone_devs

    def get_manager_info(self, email: str) -> Dict:
        """
        Get manager information for a developer.

        Args:
            email: Developer email

        Returns:
            Dictionary with manager chain information
        """
        email_lower = email.lower()

        # Check cache first
        if email_lower in self.manager_cache:
            return self.manager_cache[email_lower]

        # Find user in Azure
        azure_user = self.azure_users_by_email.get(email_lower)
        if not azure_user:
            logger.debug(f"User not found in Azure: {email}")
            self.manager_cache[email_lower] = {
                "manager": "",
                "manager_chain": "",
                "job_title": "",
                "department": "",
            }
            return self.manager_cache[email_lower]

        # Get manager chain
        user_id = azure_user.get("id")
        managers = self.azure_client.get_user_chain_of_command(user_id, max_depth=3)

        manager_names = [m.get("displayName", "") for m in managers]
        direct_manager = manager_names[0] if manager_names else ""
        manager_chain = " > ".join(manager_names) if manager_names else ""

        result = {
            "manager": direct_manager,
            "manager_chain": manager_chain,
            "job_title": azure_user.get("jobTitle", ""),
            "department": azure_user.get("department", ""),
        }

        self.manager_cache[email_lower] = result
        logger.debug(f"Retrieved manager info for {email}: {direct_manager}")
        return result

    def enrich_developer(self, dev_data: Dict) -> Dict:
        """
        Enrich developer data with manager information.

        Args:
            dev_data: Developer data from inventory

        Returns:
            Enriched developer data
        """
        email = dev_data.get("email", "")
        enriched = dict(dev_data)

        if email:
            manager_info = self.get_manager_info(email)
            enriched.update(manager_info)
        else:
            enriched.update({
                "manager": "",
                "manager_chain": "",
                "job_title": "",
                "department": "",
            })

        return enriched

    def process_all_developers(self, developers: Dict) -> Dict:
        """
        Enrich all developers with manager information.

        Args:
            developers: Dictionary of developers from inventory

        Returns:
            Dictionary of enriched developers
        """
        enriched = {}

        for dev_name, dev_data in developers.items():
            enriched[dev_name] = self.enrich_developer(dev_data)

        logger.info(f"Enriched {len(enriched)} developers with manager information")
        return enriched

    def get_summary(self, developers: Dict) -> Dict:
        """
        Get summary of changes.

        Args:
            developers: Current developers dictionary

        Returns:
            Dictionary with summary statistics
        """
        new_devs = self.identify_new_developers(developers)
        gone_devs = self.identify_gone_developers(developers)

        return {
            "total_developers": len(developers),
            "new_developers_count": len(new_devs),
            "gone_developers_count": len(gone_devs),
            "azure_total_users": len(self.azure_users),
            "timestamp": datetime.now().isoformat(),
        }
