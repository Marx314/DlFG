
import os
import logging
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

AZURE_TENANT_ID = os.getenv("AZURE_TENANT_ID")
AZURE_CLIENT_ID = os.getenv("AZURE_CLIENT_ID")
AZURE_CLIENT_SECRET = os.getenv("AZURE_CLIENT_SECRET")

SCW_API_KEY = os.getenv("SCW_API_KEY")

MICROSOFT_GRAPH_API_BASE = "https://graph.microsoft.com/v1.0"
SCW_API_BASE = "https://api.securecodewarrior.com/api/v1"

OUTPUT_DIR = os.getenv("OUTPUT_DIR", "output")
Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)

DATA_FILE = os.path.join(OUTPUT_DIR, "data.json")
REPORT_FILE = os.path.join(OUTPUT_DIR, "report.html")
WARNINGS_FILE = os.path.join(OUTPUT_DIR, "warnings.log")

MAX_RETRIES = int(os.getenv("MAX_RETRIES", 3))
INITIAL_BACKOFF = float(os.getenv("INITIAL_BACKOFF", 1.0))
MAX_BACKOFF = float(os.getenv("MAX_BACKOFF", 60.0))
EXPONENTIAL_BASE = float(os.getenv("EXPONENTIAL_BASE", 2.0))

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_LEVEL_INT = getattr(logging, LOG_LEVEL.upper(), logging.INFO)

GRAPH_PAGE_SIZE = 999

BATCH_TAG_PATTERN = r"^\d{4}-\d{2}$"


def validate_credentials() -> bool:
    required = {
        'AZURE_TENANT_ID': AZURE_TENANT_ID,
        'AZURE_CLIENT_ID': AZURE_CLIENT_ID,
        'AZURE_CLIENT_SECRET': AZURE_CLIENT_SECRET,
        'SCW_API_KEY': SCW_API_KEY,
    }

    missing = [key for key, value in required.items() if not value]
    if missing:
        logging.error(f"Missing required credentials: {', '.join(missing)}")
        return False

    return True
