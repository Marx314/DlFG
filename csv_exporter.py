"""CSV export functionality for developer inventory.

Changes:
- Always use double-quote (QUOTE_ALL) for every field
- CSV always has headers (even when appending / resuming)
- Email addresses are lowercased
- Rows sorted by email on every flush
- Files always split by commit month (one file per calendar month)
- File flushed to disk after every 10 new developers (streaming)
- Rows written as soon as they are ready, not at the end of a batch
"""

import csv
import logging
import os
from datetime import datetime
from typing import Dict, List, Optional
from config import OUTPUT_DIR, OUTPUT_FILENAME, CSV_MAX_REPOSITORIES_SHOWN, CSV_FLUSH_INTERVAL

logger = logging.getLogger(__name__)

# CSV field schema – commit_month column added for per-month split
CSV_FIELDNAMES = [
    "developer",
    "email",
    "commit_month",
    "platforms",
    "repositories",
    "commits",
    "technologies",
    "technology_count",
    "training_fit_score",
    "github_properties",
    "bitbucket_projects",
]


def _month_filename(year_month: str) -> str:
    """Return the CSV filename for a given YYYY-MM month string."""
    return f"{year_month}-developers.csv"


def _filepath(filename: str) -> str:
    return os.path.join(OUTPUT_DIR, filename)


def _ensure_output_dir() -> None:
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)


def _format_row(dev_name: str, dev_data: Dict, year_month: str) -> Dict:
    """Build a CSV row dict from enriched developer data."""
    tech_profile = dev_data.get("technology_profile", {})
    tech_list = ", ".join(
        [f"{tech}({count})" for tech, count in sorted(tech_profile.items())]
    )

    github_props = dev_data.get("github_properties", {})
    github_props_str = ""
    if github_props:
        props_list = []
        for repo, props in github_props.items():
            prop_items = [f"{k}:{v}" for k, v in props.items()]
            props_list.append(f"{repo}={{" + ", ".join(prop_items) + "}")
        github_props_str = "; ".join(props_list)

    bitbucket_projs = dev_data.get("bitbucket_projects", [])
    if isinstance(bitbucket_projs, set):
        bitbucket_projs = list(bitbucket_projs)
    bitbucket_projs_str = "; ".join(sorted(bitbucket_projs)) if bitbucket_projs else ""

    return {
        "developer": dev_name,
        "email": (dev_data.get("email") or "unknown").lower().strip(),
        "commit_month": year_month,
        "platforms": "; ".join(dev_data.get("platforms", [])),
        "repositories": "; ".join(dev_data.get("repositories", [])[:CSV_MAX_REPOSITORIES_SHOWN]),
        "commits": dev_data.get("commits", 0),
        "technologies": tech_list,
        "technology_count": len(tech_profile),
        "training_fit_score": dev_data.get("training_fit_score", 0),
        "github_properties": github_props_str,
        "bitbucket_projects": bitbucket_projs_str,
    }


class MonthFileHandle:
    """Manages one per-month CSV file.

    Guarantees:
    - Header row always present at the top of the file.
    - Every field double-quoted (csv.QUOTE_ALL).
    - File sorted by email on every flush.
    - Flushed after every FLUSH_EVERY_N_DEVELOPERS new rows.
    - Written row-by-row as commits are processed (streaming).
    """

    def __init__(self, year_month: str):
        self.year_month = year_month
        self.filename = _month_filename(year_month)
        self.filepath = _filepath(self.filename)
        self._csvfile = None
        self._writer = None
        self._written_emails: set = set()
        self._pending: List[Dict] = []
        self._new_since_flush = 0

    def open(self) -> None:
        _ensure_output_dir()
        if os.path.exists(self.filepath):
            self._load_existing()
        # Always open in write mode — we rewrite sorted on every flush
        self._csvfile = open(self.filepath, "w", newline="", encoding="utf-8")
        self._writer = csv.DictWriter(
            self._csvfile, fieldnames=CSV_FIELDNAMES, quoting=csv.QUOTE_ALL
        )
        self._writer.writeheader()
        # Re-write existing rows immediately so file is never left without data
        if self._pending:
            self._writer.writerows(self._pending)
            self._csvfile.flush()
        logger.info(f"Opened month file: {self.filepath}")

    def _load_existing(self) -> None:
        """Read existing rows back into _pending so they survive the rewrite."""
        try:
            with open(self.filepath, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    email = (row.get("email") or "").lower().strip()
                    if email and email not in self._written_emails:
                        row["email"] = email
                        self._pending.append(dict(row))
                        self._written_emails.add(email)
            logger.info(
                f"Loaded {len(self._pending)} existing rows from {self.filepath}"
            )
        except IOError as e:
            logger.warning(f"Could not load existing month file: {e}")

    def write_developer(self, dev_name: str, dev_data: Dict) -> bool:
        """Stream-write one developer row.

        Returns True when the row is new; False for a duplicate email.
        Triggers a sorted flush every CSV_FLUSH_INTERVAL new rows.
        """
        if not self._writer:
            raise RuntimeError("MonthFileHandle not open — call open() first")

        email = (dev_data.get("email") or "unknown").lower().strip()
        if email in self._written_emails:
            logger.debug(f"Skipping duplicate email: {email}")
            return False

        row = _format_row(dev_name, dev_data, self.year_month)
        self._pending.append(row)
        self._written_emails.add(email)
        self._new_since_flush += 1

        # Write the row immediately (streaming) without waiting for a full flush
        self._writer.writerow(row)
        self._csvfile.flush()
        logger.debug(f"Wrote developer immediately: {email}")

        if self._new_since_flush >= CSV_FLUSH_INTERVAL:
            self._flush_sorted()

        return True

    def _flush_sorted(self) -> None:
        """Rewrite the whole file sorted by email, reset flush counter."""
        if not self._csvfile:
            return
        sorted_rows = sorted(self._pending, key=lambda r: r.get("email", "").lower())
        self._csvfile.seek(0)
        self._csvfile.truncate()
        self._writer.writeheader()
        self._writer.writerows(sorted_rows)
        self._csvfile.flush()
        self._new_since_flush = 0
        logger.info(
            f"Flushed & sorted {len(sorted_rows)} developers in {self.filepath}"
        )

    def close(self) -> None:
        if self._csvfile:
            self._flush_sorted()
            self._csvfile.close()
            self._csvfile = None
            self._writer = None
            logger.info(f"Closed month file: {self.filepath}")

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


class CSVExporter:
    """Export developer inventory to per-month CSV files.

    One file per calendar month derived from each commit's date.
    Files are streamed row-by-row and flushed/sorted every
    FLUSH_EVERY_N_DEVELOPERS new rows.
    """

    def __init__(self, filename: str = None):
        self.default_filename = filename or OUTPUT_FILENAME
        self._handles: Dict[str, MonthFileHandle] = {}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def open(self) -> None:
        _ensure_output_dir()

    def _get_handle(self, year_month: str) -> MonthFileHandle:
        if year_month not in self._handles:
            handle = MonthFileHandle(year_month)
            handle.open()
            self._handles[year_month] = handle
        return self._handles[year_month]

    def write_developer(
        self, dev_name: str, dev_data: Dict, year_month: str = None
    ) -> bool:
        """Write a developer to the correct per-month file.

        year_month: 'YYYY-MM' — derived from the developer's latest commit
        date when available; falls back to the current calendar month.
        """
        if year_month is None:
            latest = dev_data.get("latest_commit_date", "")
            if latest and len(latest) >= 7:
                year_month = latest[:7]
            else:
                year_month = datetime.utcnow().strftime("%Y-%m")

        handle = self._get_handle(year_month)
        return handle.write_developer(dev_name, dev_data)

    def close(self) -> None:
        for handle in self._handles.values():
            handle.close()
        self._handles.clear()

    # ------------------------------------------------------------------
    # Static helpers
    # ------------------------------------------------------------------

    @staticmethod
    def export_summary(stats: Dict, filename: str = None) -> str:
        if filename is None:
            filename = OUTPUT_FILENAME.replace(".csv", "_summary.csv")
        filepath = _filepath(filename)
        _ensure_output_dir()
        try:
            with open(filepath, "w", newline="", encoding="utf-8") as csvfile:
                writer = csv.DictWriter(
                    csvfile, fieldnames=list(stats.keys()), quoting=csv.QUOTE_ALL
                )
                writer.writeheader()
                writer.writerow(stats)
            logger.info(f"Exported summary to {filepath}")
            return filepath
        except IOError as e:
            logger.error(f"Failed to export summary: {e}")
            raise
