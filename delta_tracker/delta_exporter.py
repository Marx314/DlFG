"""Export delta tracking results and enriched CSV."""

import csv
import logging
import os
from typing import Dict, List
from datetime import datetime
from config import OUTPUT_DIR, DELTA_OUTPUT_DIR, TRACKING_FILENAME

logger = logging.getLogger(__name__)


class DeltaExporter:
    """Export delta tracking and enriched developer CSV."""

    @staticmethod
    def ensure_output_dirs() -> None:
        """Ensure output directories exist."""
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        os.makedirs(DELTA_OUTPUT_DIR, exist_ok=True)
        logger.info(f"Output directories ready: {DELTA_OUTPUT_DIR}")

    @staticmethod
    def export_enriched_csv(
        developers: Dict,
        output_filename: str = None,
        output_dir: str = OUTPUT_DIR
    ) -> str:
        """
        Export enriched developer CSV with manager information.

        Args:
            developers: Dictionary of enriched developers
            output_filename: Output filename
            output_dir: Output directory

        Returns:
            Path to exported CSV
        """
        output_filename = output_filename or f"{datetime.now().strftime('%Y-%m')}-developers-enriched.csv"
        filepath = os.path.join(output_dir, output_filename)

        fieldnames = [
            "developer",
            "email",
            "platforms",
            "repositories",
            "commits",
            "technologies",
            "technology_count",
            "training_fit_score",
            "manager",
            "manager_chain",
            "job_title",
            "department",
        ]

        rows = []
        for dev_name, dev_data in developers.items():
            row = {
                "developer": dev_name,
                "email": dev_data.get("email", ""),
                "platforms": "; ".join(dev_data.get("platforms", [])),
                "repositories": "; ".join(dev_data.get("repositories", [])[:10]),
                "commits": dev_data.get("commits", 0),
                "technologies": dev_data.get("technologies", ""),
                "technology_count": dev_data.get("technology_count", 0),
                "training_fit_score": dev_data.get("training_fit_score", 0),
                "manager": dev_data.get("manager", ""),
                "manager_chain": dev_data.get("manager_chain", ""),
                "job_title": dev_data.get("job_title", ""),
                "department": dev_data.get("department", ""),
            }
            rows.append(row)

        # Sort by training fit score
        rows.sort(key=lambda x: x["training_fit_score"], reverse=True)

        try:
            with open(filepath, "w", newline="", encoding="utf-8") as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)

            logger.info(f"Exported {len(rows)} enriched developers to {filepath}")
            return filepath

        except IOError as e:
            logger.error(f"Failed to export enriched CSV: {e}")
            raise

    @staticmethod
    def export_delta_tracking(
        new_developers: List[str],
        gone_developers: List[tuple],
        summary: Dict,
        output_filename: str = None,
        output_dir: str = DELTA_OUTPUT_DIR
    ) -> str:
        """
        Export delta tracking report.

        Args:
            new_developers: List of new developer names
            gone_developers: List of (name, date) tuples for gone developers
            summary: Summary statistics
            output_filename: Output filename
            output_dir: Output directory

        Returns:
            Path to exported delta CSV
        """
        output_filename = output_filename or TRACKING_FILENAME
        filepath = os.path.join(output_dir, output_filename)

        rows = []

        # New developers
        for dev_name in new_developers:
            rows.append({
                "developer": dev_name,
                "status": "NEW",
                "date": datetime.now().strftime("%Y-%m-%d"),
                "notes": "New developer identified in inventory",
            })

        # Gone developers
        for dev_name, last_seen in gone_developers:
            rows.append({
                "developer": dev_name,
                "status": "GONE",
                "date": last_seen,
                "notes": f"No commits found in {summary.get('threshold_days', 90)} days",
            })

        fieldnames = ["developer", "status", "date", "notes"]

        try:
            with open(filepath, "w", newline="", encoding="utf-8") as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)

            logger.info(f"Exported delta tracking ({len(rows)} changes) to {filepath}")
            return filepath

        except IOError as e:
            logger.error(f"Failed to export delta tracking: {e}")
            raise

    @staticmethod
    def export_summary(summary: Dict, output_filename: str = None, output_dir: str = DELTA_OUTPUT_DIR) -> str:
        """
        Export summary statistics.

        Args:
            summary: Summary dictionary
            output_filename: Output filename
            output_dir: Output directory

        Returns:
            Path to exported summary CSV
        """
        output_filename = output_filename or f"{datetime.now().strftime('%Y-%m-%d')}-delta-summary.csv"
        filepath = os.path.join(output_dir, output_filename)

        try:
            with open(filepath, "w", newline="", encoding="utf-8") as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=summary.keys())
                writer.writeheader()
                writer.writerow(summary)

            logger.info(f"Exported delta summary to {filepath}")
            return filepath

        except IOError as e:
            logger.error(f"Failed to export summary: {e}")
            raise
