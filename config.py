"""Configuration module for Developers Security Training Inventory."""

import os
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

# Days lookback for commit analysis (configurable)
DAYS_LOOKBACK = int(os.getenv("DAYS_LOOKBACK", 90))

# Calculate since date
SINCE_DATE = (datetime.utcnow() - timedelta(days=DAYS_LOOKBACK)).isoformat() + "Z"

# API Credentials - Support multiple tokens for rate limit handling
# GitHub: Can provide multiple tokens separated by comma
# Example: GITHUB_TOKEN="token1,token2,token3"
GITHUB_TOKENS = [
    t.strip() for t in os.getenv("GITHUB_TOKEN", "").split(",") if t.strip()
]
GITHUB_TOKEN = GITHUB_TOKENS[0] if GITHUB_TOKENS else None

# Bitbucket Server configuration (not Cloud)
# Projects are queried directly; all projects included
BITBUCKET_URL = os.getenv("BITBUCKET_URL", "https://bitbucket.internal")
BITBUCKET_USER = os.getenv("BITBUCKET_USER")
BITBUCKET_PASS = os.getenv("BITBUCKET_PASS")

# Bitbucket: Support multiple passwords/tokens (for app passwords or API tokens)
# Example: BITBUCKET_PASS="pass1,pass2,pass3"
BITBUCKET_PASSES = [
    p.strip() for p in os.getenv("BITBUCKET_PASS", "").split(",") if p.strip()
]

# API Endpoints
GITHUB_API_BASE = "https://api.github.com"
BITBUCKET_API_BASE = f"{BITBUCKET_URL}/rest/api/1.0"  # Bitbucket Server uses 1.0

# Output configuration
OUTPUT_DIR = os.getenv("OUTPUT_DIR", "output")
OUTPUT_FILENAME = f"{datetime.now().strftime('%Y-%m')}-developers.csv"

# Technology classifications (file extensions -> language)
TECH_EXTENSIONS = {
    ".py": "Python",
    ".js": "JavaScript",
    ".ts": "TypeScript",
    ".jsx": "React",
    ".tsx": "React",
    ".java": "Java",
    ".go": "Go",
    ".rs": "Rust",
    ".cpp": "C++",
    ".c": "C",
    ".cs": "C#",
    ".php": "PHP",
    ".rb": "Ruby",
    ".sh": "Shell",
    ".yaml": "YAML",
    ".yml": "YAML",
    ".json": "JSON",
    ".sql": "SQL",
    ".html": "HTML",
    ".css": "CSS",
}

# API Rate Limiting
GITHUB_RATE_LIMIT = 5000  # per hour (authenticated)
BITBUCKET_RATE_LIMIT = 1000  # per hour (typical)

# Filtering
EXCLUDE_ARCHIVED = True
EXCLUDE_FORKS = True
MIN_COMMITS = 1  # Minimum commits to include developer

# GitHub Custom Properties to capture
# Leave empty to skip, or specify comma-separated property names
# Example: "security,team,environment"
GITHUB_CUSTOM_PROPERTIES = [
    p.strip() for p in os.getenv("GITHUB_CUSTOM_PROPERTIES", "").split(",") if p.strip()
]

# Service Account Filtering
# Patterns to exclude from training analysis (case-insensitive)
# Matches against both username and email (supports wildcards)
# Default: common bot/service account patterns + GitHub noreply emails
SERVICE_ACCOUNT_PATTERNS = [
    p.strip() for p in os.getenv(
        "SERVICE_ACCOUNT_PATTERNS",
        "bot-*,*-bot,*bot*,service-*,*-service,automation-*,*automation*,ci-*,*-ci,deploy*,*deploy,github-*,bitbucket-*,*users.noreply.github.com,github@*"
    ).split(",") if p.strip()
]

# Retry Configuration
MAX_RETRIES = int(os.getenv("MAX_RETRIES", 5))
INITIAL_BACKOFF = float(os.getenv("INITIAL_BACKOFF", 1.0))
MAX_BACKOFF = float(os.getenv("MAX_BACKOFF", 300.0))
EXPONENTIAL_BASE = float(os.getenv("EXPONENTIAL_BASE", 2.0))

# Logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_DIR = os.getenv("LOG_DIR", "logs")
LOG_FILE = os.path.join(LOG_DIR, f"inventory_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")

# API Pagination
GITHUB_PAGINATION_SIZE = 100
BITBUCKET_PAGINATION_SIZE = 50

# Timestamp handling
BITBUCKET_TIMESTAMP_DIVISOR = 1000  # milliseconds to seconds

# Training fit scoring
TRAINING_FIT_COMMIT_MULTIPLIER = 7
TRAINING_FIT_COMMIT_MAX_SCORE = 70
TRAINING_FIT_REPO_MULTIPLIER = 10
TRAINING_FIT_REPO_MAX_SCORE = 30

# CSV export
CSV_MAX_REPOSITORIES_SHOWN = 10
CSV_FLUSH_INTERVAL = 10  # developers between flushes

# Language detection
BITBUCKET_LANGUAGE_DIVISOR = 1000

# Commit caching
COMMIT_CACHE_DIR = os.getenv("COMMIT_CACHE_DIR", "output/commit_cache")
COMMIT_CACHE_ENABLED = os.getenv("COMMIT_CACHE_ENABLED", "true").lower() == "true"
