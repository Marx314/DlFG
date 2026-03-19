"""Configuration for delta tracker module."""

import os
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

# Azure/Microsoft Graph API configuration
AZURE_TENANT_ID = os.getenv("AZURE_TENANT_ID")
AZURE_CLIENT_ID = os.getenv("AZURE_CLIENT_ID")
AZURE_CLIENT_SECRET = os.getenv("AZURE_CLIENT_SECRET")
AZURE_GRAPH_ENDPOINT = os.getenv("AZURE_GRAPH_ENDPOINT", "https://graph.microsoft.com/v1.0")

# Days to consider a developer as "gone" if no commits found
DAYS_INACTIVE = int(os.getenv("DAYS_INACTIVE", 90))

# Output paths
OUTPUT_DIR = os.getenv("OUTPUT_DIR", "output")
DELTA_OUTPUT_DIR = os.path.join(OUTPUT_DIR, "delta_tracking")

# Tracking filename
TRACKING_FILENAME = f"{datetime.now().strftime('%Y-%m-%d')}-delta.csv"

# Parent directory for loading source CSV
PARENT_OUTPUT_DIR = os.getenv("PARENT_OUTPUT_DIR", "..")

# Logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
