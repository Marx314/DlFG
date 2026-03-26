# Training Compliance Dashboard Pipeline

A Python data pipeline that pulls training compliance data from Microsoft Entra ID and Secure Code Warrior, normalizes it into a unified schema, and generates a self-contained HTML compliance report.

## Features

- **Dual-source data integration**: Fetches users from Microsoft Entra ID and training data from Secure Code Warrior
- **Manager chain tracking**: Automatically walks Entra ID manager hierarchy (up to 4 levels) to build organizational structure
- **Organizational history tracking**: Tracks when developers' organizational positions change
- **Normalized schema**: Unified data model with Training, InvitationBatch, Developer, DeveloperOrgHistory, and TrainingRecord tables
- **Status derivation**: Automatically computes training status (departed, exempt, completed, overdue, pending)
- **Self-contained HTML report**: Single-file report with inline CSS/JS, no external dependencies
- **Interactive report**: VP/director drill-down, sortable columns, completion metrics, comparison panel
- **Retry resilience**: Automatic retry with exponential backoff for API failures
- **Comprehensive logging**: Console and file logging with warnings file for non-fatal issues

## Quick Start

### Prerequisites

- Python 3.8+
- Microsoft Entra ID app registration with credentials
- Secure Code Warrior API key

### Installation

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # or: venv\Scripts\activate on Windows

# Install dependencies
pip install -r requirements.txt
```

### Configuration

```bash
# Copy template and fill in credentials
cp .env.example .env

# Edit .env with your credentials:
# AZURE_TENANT_ID=your-tenant-id
# AZURE_CLIENT_ID=your-client-id
# AZURE_CLIENT_SECRET=your-client-secret
# SCW_API_KEY=your-scw-api-key
```

### Running the Pipeline

```bash
# Run the pipeline
python main.py

# Outputs generated:
# - output/data.json          (normalized dataset)
# - output/report.html        (compliance report)
# - output/warnings.log       (any warnings or errors)
```

## Architecture

### Module Structure

| Module | Purpose |
|--------|---------|
| `models.py` | Data schema definitions (Training, Developer, etc.) |
| `config.py` | Environment variables and configuration |
| `entra.py` | Microsoft Graph API client for Entra ID |
| `scw.py` | Secure Code Warrior API client |
| `normalize.py` | Data aggregation, joining, and normalization |
| `report.py` | HTML report generation |
| `retry_handler.py` | Retry logic with exponential backoff |
| `main.py` | Pipeline orchestrator (entry point) |

### Data Flow

```
Entra ID API ──→ Fetch users + walk manager chains
     ↓
SCW API ──→ Fetch tags + user completion records
     ↓
Normalize ──→ Join on email, build org history, derive status
     ↓
Output JSON ──→ output/data.json (source of truth)
     ↓
Generate Report ──→ output/report.html (interactive HTML)
```

## Data Schema

### Training
```python
id: str
name: str
training_year: int
type: str
```

### InvitationBatch
```python
id: str
training_id: str
batch_code: str  # YYYY-MM format from SCW tag
invited_on: date
due_date: date
notes: Optional[str]
```

### Developer
```python
id: str
email: str
full_name: str
is_active: bool
left_on: Optional[date]
exemption_start: Optional[date]
exemption_end: Optional[date]
exemption_reason: Optional[str]
```

### DeveloperOrgHistory
```python
id: str
developer_id: str
manager_email: Optional[str]      # Level 0
director: Optional[str]           # Level 1
principal_director: Optional[str] # Level 2
vp: Optional[str]                 # Level 3
effective_from: date
effective_to: Optional[date]      # NULL = current
```

### TrainingRecord
```python
id: str
developer_id: str
invitation_batch_id: str
completed: bool
completion_date: Optional[date]
attempts: int
last_reminder_sent: Optional[date]
reminders_sent_count: int
```

## Training Status Logic

Status is automatically derived (not stored) using this priority order:

1. **Departed** — Developer is no longer active (`is_active=false`)
2. **Exempt** — Developer has active exemption (`exemption_start` set, `exemption_end` null)
3. **Completed** — Training record shows `completed=true`
4. **Overdue** — Due date has passed, training not completed
5. **Pending** — Due date in future, training not completed

## HTML Report Features

### Header
- Training name and year
- Generation timestamp
- Summary metrics (completion rate, counts by status)

### VP Organization Chart
- Completion rate by VP
- Click VP to expand and view directors
- Director-level completion rates

### Comparison Panel
- Selected organization completion rate
- Company-wide completion rate

### Needs Attention
- Developers who are overdue
- Developers with 2+ attempts still pending
- Shows name, director, status, and attempt count

### Developer Table
- Two tabs: Active and Departed
- Columns: name, email, director, VP, batch, due date, status badge, completion date, attempts
- Sortable by clicking column headers
- Color-coded status badges:
  - Green: Completed
  - Red: Overdue
  - Amber: Pending
  - Gray: Exempt/Departed

## API Integration Details

### Entra ID / Microsoft Graph

- **Authentication**: Client credentials flow (app-only)
- **Endpoint**: `https://graph.microsoft.com/v1.0`
- **Users fetch**: GET `/users` with pagination
- **Manager chain**: GET `/users/{id}?$expand=manager` (recursive walk)
- **Manager chain depth**: Up to 4 levels (manager, director, principal_director, vp)
- **Handling short chains**: Fill from top down, null for missing levels

### Secure Code Warrior

- **Authentication**: Bearer token (API key)
- **Base URL**: `https://api.securecodewarrior.com/api/v1`
- **Tags fetch**: GET `/tags` (returns invitation batches)
- **User records**: GET `/users?tag={tag_id}` (returns completion data per tag)
- **Batch identification**: Tags matching YYYY-MM pattern are invitation batches
- **Due date calculation**: Last day of month, 2 months after batch month

## Retry & Error Handling

- **Transient errors**: Network errors, 429 (rate limit), 5xx (server errors), 408/504 (timeouts)
- **Retry strategy**: Exponential backoff with jitter (configurable)
- **Max retries**: 3 (default, configurable)
- **Non-fatal errors**: Logged as warnings, pipeline continues:
  - SCW users with no Entra match → warning, skipped
  - Manager chain walk failure → uses partial chain
  - Missing fields → uses null/default
- **Fatal errors**: Pipeline exits with code 1:
  - Missing credentials
  - Entra ID pagination fails
  - SCW has no matching tags
  - Top-level exception (printed with context)

## Logging

All output goes to both **console** and **warnings.log** file in output directory:

- **DEBUG**: API calls, data processing details
- **INFO**: High-level progress (fetched X users, normalized Y records, etc.)
- **WARNING**: Non-fatal issues (unmatched emails, parsing errors)
- **ERROR**: Fatal errors that cause pipeline to fail

Control logging level with `LOG_LEVEL` env var (default: INFO).

## Output Files

### `output/data.json`
Complete normalized dataset in JSON format. Schema includes:
- `trainings`: List of Training records
- `invitation_batches`: List of InvitationBatch records
- `developers`: List of Developer records
- `org_history`: List of DeveloperOrgHistory records
- `training_records`: List of TrainingRecord records

This is the source of truth and can be used for further analysis.

### `output/report.html`
Self-contained HTML report with:
- Inline CSS (no external stylesheets)
- Inline JavaScript (no external scripts)
- Embedded data (no API calls from browser)
- Print-friendly styling (works well when printed to PDF)
- No external dependencies (works offline, can be emailed)

### `output/warnings.log`
Log file containing all INFO, WARNING, and ERROR messages from the run.

## Development

### Testing

Run with a small dataset for faster iteration:

```bash
export AZURE_TENANT_ID=...
export AZURE_CLIENT_ID=...
export AZURE_CLIENT_SECRET=...
export SCW_API_KEY=...
python main.py
```

Enable debug logging:

```bash
export LOG_LEVEL=DEBUG
python main.py
```

### Extending the Pipeline

To add new fields or features:

1. **New schema field**: Add to dataclass in `models.py`
2. **New API data**: Update `entra.py` or `scw.py` to fetch it
3. **New processing logic**: Update `normalize.py` to process the data
4. **Report changes**: Update `report.py` to display it

## Troubleshooting

### "Missing required credentials"
- Ensure all 4 env vars are set: AZURE_TENANT_ID, AZURE_CLIENT_ID, AZURE_CLIENT_SECRET, SCW_API_KEY
- Check `.env` file is in same directory as main.py

### "No SCW tags matching YYYY-MM pattern found"
- Verify SCW has tags created in YYYY-MM format (e.g., 2026-03)
- Check SCW_API_KEY is correct

### "SCW user {email} not found in Entra ID"
- This is a warning (logged in warnings.log)
- User exists in SCW but not in Entra ID
- Pipeline skips this user for training record (no phantom developer created)

### API timeouts or rate limits
- Increase MAX_RETRIES or MAX_BACKOFF if needed
- For rate limits: implement credential rotation (future enhancement)

## Performance

- **Typical run**: 5-15 minutes depending on org size
- **Users processed**: Usually 50-1000+ developers
- **API calls**:
  - Entra: 1 paginated call for users + 1 call per user for manager chain
  - SCW: 1 call for tags + 1 call per tag for users
  - Total: N + M API calls (N = users, M = tags)

## Future Enhancements

- [ ] Incremental mode (only fetch users/records updated since last run)
- [ ] Email report delivery
- [ ] Slack notifications for managers about their team's compliance
- [ ] Microsoft List integration for live dashboard
- [ ] Configurable training fit scoring
- [ ] Support for multiple training programs
- [ ] Export to Microsoft Excel format
- [ ] Manager notifications for overdue direct reports
