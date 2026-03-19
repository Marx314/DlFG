# Developers Security Training Inventory

Enterprise-grade platform for automated security training assessment and developer profiling across GitHub and Bitbucket.

## Overview

Developers Security Training Inventory identifies and scores developers for Secure Code Warrior security training by analyzing their activity across GitHub and Bitbucket repositories. The system:

- **Aggregates** developer commit history from both platforms
- **Profiles** technology adoption and development patterns
- **Scores** training suitability based on activity, language diversity, and repository engagement
- **Enriches** with organizational hierarchy and manager chain (via Azure AD)
- **Filters** service accounts and bots automatically
- **Tracks** developer changes over time with delta detection
- **Exports** structured CSV data for downstream reporting and integration

## Quick Start

### Prerequisites

- Python 3.8+
- GitHub API token (for GitHub access)
- Bitbucket credentials (username/password or API token for internal instance)
- Optional: Azure AD credentials (for manager enrichment via delta tracker)

### Installation

```bash
# Clone repository
git clone <repo-url>
cd developers-security-training-inventory

# Install dependencies
pip install -r requirements.txt
```

### Basic Usage

```bash
# Set up credentials
export GITHUB_SCOPE="your-org-name"
export GITHUB_TOKEN="your-github-token"
export BITBUCKET_SCOPE="your-workspace"
export BITBUCKET_USER="your-username"
export BITBUCKET_PASS="your-password-or-token"

# Run inventory analysis
python main.py
```

Output: `output/YYYY-MM-developers.csv`

## Configuration

### Environment Variables

#### Core Configuration
| Variable | Default | Description |
|----------|---------|-------------|
| `GITHUB_SCOPE` | - | GitHub organization(s) to query (comma-separated) |
| `GITHUB_TOKEN` | - | GitHub API token(s) for authentication (comma-separated for multiple) |
| `BITBUCKET_SCOPE` | - | Bitbucket workspace(s) to query |
| `BITBUCKET_USER` | - | Bitbucket username |
| `BITBUCKET_PASS` | - | Bitbucket password/token(s) (comma-separated) |
| `DAYS_LOOKBACK` | 90 | Days of commit history to analyze |

#### GitHub Custom Properties
| Variable | Example | Description |
|----------|---------|-------------|
| `GITHUB_CUSTOM_PROPERTIES` | security,team | Comma-separated list of custom property names to capture |

#### Service Account Filtering
| Variable | Default | Description |
|----------|---------|-------------|
| `SERVICE_ACCOUNT_PATTERNS` | bot-*,service-*,... | Comma-separated wildcard patterns for accounts to exclude |

#### Retry & Resilience
| Variable | Default | Description |
|----------|---------|-------------|
| `MAX_RETRIES` | 5 | Maximum retry attempts for failed API calls |
| `INITIAL_BACKOFF` | 1.0 | Initial backoff time in seconds |
| `MAX_BACKOFF` | 300.0 | Maximum backoff time in seconds |
| `EXPONENTIAL_BASE` | 2.0 | Exponential backoff multiplier |

#### Advanced
| Variable | Default | Description |
| `OUTPUT_DIR` | output | Directory for CSV output |
| `LOG_LEVEL` | INFO | Logging level (DEBUG, INFO, WARNING, ERROR) |

### Example Configurations

**Full Setup with Custom Properties:**
```bash
export GITHUB_SCOPE="myorg,anotherorg"
export GITHUB_TOKEN="token1,token2,token3"
export GITHUB_CUSTOM_PROPERTIES="security,team,environment"
export BITBUCKET_SCOPE="myworkspace"
export BITBUCKET_USER="username"
export BITBUCKET_PASS="pass1,pass2"
export DAYS_LOOKBACK="180"
export SERVICE_ACCOUNT_PATTERNS="bot-*,ci-*,automation-*,jenkins-*"
export MAX_RETRIES="10"

python main.py
```

**GitHub-Only Inventory:**
```bash
export GITHUB_SCOPE="enterprise-org"
export GITHUB_TOKEN="ghp_xxxxx"
python main.py
```

**Bitbucket-Only Inventory:**
```bash
export BITBUCKET_SCOPE="engineering"
export BITBUCKET_USER="analyst"
export BITBUCKET_PASS="xxxxx"
python main.py
```

## Output Files

### Main Inventory (`output/YYYY-MM-developers.csv`)

| Column | Description | Example |
|--------|-------------|---------|
| developer | Developer name | John Doe |
| email | Email address | john.doe@company.com |
| platforms | Platforms active on | GitHub; Bitbucket |
| repositories | Contributed repositories | repo1; repo2; repo3 |
| commits | Total commits analyzed | 45 |
| technologies | Technologies with counts | Python(32), JavaScript(8) |
| technology_count | Unique technology count | 2 |
| training_fit_score | Training suitability (0-100) | 78.5 |
| github_properties | GitHub custom properties | org/repo={security:critical} |
| bitbucket_projects | Bitbucket projects | MYPROJ/My Project; OTHPROJ/Other |

### Enriched Inventory (via Delta Tracker)

Additional columns from `delta_tracker/`:
- `manager` - Direct manager name
- `manager_chain` - Full chain of command
- `job_title` - Job title from Azure AD
- `department` - Department from Azure AD

### Delta Tracking (`output/delta_tracking/YYYY-MM-DD-delta.csv`)

Tracks changes:
| Column | Description |
|--------|-------------|
| developer | Developer name |
| status | NEW (not in Azure) or GONE (inactive) |
| date | Identification date |
| notes | Status reason |

## Features

### Language Detection (Technology Profiling)

Automatically detects programming languages and technologies using:

**GitHub**: GitHub's built-in linguist API (uses byte-count analysis)
- Returns accurate language breakdown per repository
- Covers 500+ languages and frameworks

**Bitbucket**: File extension-based detection
- Analyzes repository file tree
- Maps extensions to 40+ languages (Python, JavaScript, Java, Go, Rust, etc.)
- Works across all repository sizes

Each developer's technology profile aggregates languages from all their contributed repositories.

### Service Account Filtering
Automatically excludes non-human accounts:
```
Excluded by default:
- bot-*, *-bot, *bot*
- service-*, *-service
- automation-*, *automation*
- ci-*, *-ci, deploy*, *deploy
- github-*, bitbucket-*
```

Customize with: `export SERVICE_ACCOUNT_PATTERNS="my-pattern-*,*-custom"`

### Repository Filtering
Excludes from analysis:
- Archived repositories
- Forked repositories
- QA/test repositories (configurable via `excluded_repos.json`)

### Multi-Token Support
Rotate through multiple API tokens to work around rate limits:
```bash
# 3 GitHub tokens = ~3x rate limit capacity
export GITHUB_TOKEN="token1,token2,token3"
```

Automatic rotation on HTTP 429 (rate limit) response.

### Retry Logic
Transient failures automatically retried:
- Network timeouts
- DNS failures
- HTTP 5xx errors
- Rate limiting (429)

Configurable exponential backoff with jitter.

### Repository Migration Detection
Detects when repositories migrate between platforms by comparing commit hashes:
```
PROBABLE: github.com/org/service <-> bitbucket.org/team/service (42 shared commits)
POSSIBLE: github.com/org/tool <-> bitbucket.org/team/tool (3 shared commits)
```

## Architecture

```
main.py (Entry point)
├── github_client.py (GitHub API with retry/token rotation)
├── bitbucket_client.py (Bitbucket API with retry/token rotation)
├── data_processor.py (Profile aggregation & scoring)
├── csv_exporter.py (Streaming CSV output)
├── migration_tracker.py (Repository migration detection)
├── service_account_filter.py (Bot/service account filtering)
├── excluded_repos_config.py (External repo exclusion rules)
└── retry_handler.py (Resilience & token rotation)

delta_tracker/ (Separate module)
├── main.py (Delta tracking entry point)
├── azure_client.py (Azure AD integration)
├── delta_processor.py (Change detection)
└── delta_exporter.py (Enriched CSV output)
```

## Resumable Checkpoints

Kill and resume the process at any time. Progress is automatically saved.

**How it works:**
- Progress checkpoint saved to `output/checkpoint.json`
- Tracks which repositories have been processed
- On restart, automatically skips completed repos
- No data loss on interruption

**Usage:**
```bash
# Start the inventory (Ctrl+C to interrupt)
export GITHUB_SCOPE="myorg"
python main.py

# Later: Resume from where you left off
python main.py
# Logs will show: "Resuming from checkpoint: X GitHub repos, Y Bitbucket repos, Z developers processed"

# Or start fresh and clear the checkpoint
python main.py --clear-checkpoint
```

## Persistence & Incremental Updates

**Intelligent Caching:**
- First run: Queries GitHub/Bitbucket, saves to `YYYY-MM-developers.csv`
- Subsequent runs same month: Loads from cache (no API queries)
- Next month: Fresh queries for new month's CSV

**Streaming Export:**
- Developers written to CSV as processed (no memory bloat)
- Safe interruption/resume capability
- Deduplication across platforms

## Delta Tracking Module

Separate module for tracking developer changes and enriching with organizational data:

```bash
cd delta_tracker
export AZURE_TENANT_ID="your-tenant-id"
export AZURE_CLIENT_ID="your-client-id"
export AZURE_CLIENT_SECRET="your-client-secret"
python main.py
```

Outputs:
- Enriched CSV with manager chain and department
- Delta tracking (new/gone developers)
- Summary statistics

See `delta_tracker/README.md` for details.

## Examples

### Identify High-Priority Training Candidates

Filter CSV for top scorers:
```bash
tail -n +2 output/YYYY-MM-developers.csv | \
  sort -t',' -k8 -nr | \
  head -20
```

### Find Developers by Technology

```bash
grep "Python" output/YYYY-MM-developers.csv | cut -d',' -f1,7
```

### Export to Secure Code Warrior

Use enriched CSV with manager information:
```bash
python delta_tracker/main.py
# Use output/YYYY-MM-developers-enriched.csv for SCW import
```

### Track Training Progress Over Time

Compare delta files:
```bash
# NEW developers this month
grep "NEW" output/delta_tracking/2026-03-*.csv

# GONE developers (inactive)
grep "GONE" output/delta_tracking/2026-03-*.csv
```

## Troubleshooting

### "No developer data collected"
- Verify GitHub/Bitbucket scopes are correct
- Check credentials are valid
- Review logs for API errors: `export LOG_LEVEL=DEBUG`

### "Rate limited" messages
- Add more API tokens: `export GITHUB_TOKEN="token1,token2,token3"`
- Reduce `DAYS_LOOKBACK` to query fewer commits
- Retry automatically; monitor logs

### CSV column too wide
- Limit `SERVICE_ACCOUNT_PATTERNS` to reduce noise
- Select fewer `GITHUB_CUSTOM_PROPERTIES`
- Bitbucket projects are already deduplicated

### Azure AD enrichment fails
- Verify service principal credentials
- Check permissions: `User.Read.All`, `Directory.Read.All`
- Review `delta_tracker/README.md`

## Performance Considerations

**API Usage:**
- Single token: ~5,000 req/hour (GitHub), ~1,000 req/hour (Bitbucket)
- Three tokens: ~15,000 req/hour (GitHub)

**Caching:**
- First run (90 days lookback): ~5-30 minutes (depends on orgs)
- Same-month reruns: <1 second (cache hit)
- Next month: ~5-30 minutes (fresh query)

**Memory:**
- Streaming export: ~5MB per 1,000 developers
- Minimal during CSV writing

## Future Enhancements

- [ ] Microsoft List integration for live dashboards
- [ ] Confluence reporting templates
- [ ] Configurable training fit algorithms
- [ ] Slack notifications for new/gone developers
- [ ] GraphQL support for GitHub (reduce API calls)
- [ ] Database backend option (vs CSV)
- [ ] Web UI for filtering and analysis

## Security Notes

- **Credentials**: Store API tokens in environment variables, not in code
- **Rate Limits**: Use multiple tokens to avoid hitting limits
- **Service Accounts**: Automatically filtered to avoid false positives
- **Data**: CSV files contain developer activity; handle appropriately for your organization

## Support & Feedback

For issues, feature requests, or questions:
1. Check logs with `LOG_LEVEL=DEBUG`
2. Review configuration in CLAUDE.md and delta_tracker/README.md
3. Verify API credentials and permissions
4. Consult troubleshooting section above
