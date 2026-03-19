"""
Delta Tracker - Identify new/gone developers and enrich with manager information.

Loads developer inventory CSV, queries Azure AD for manager information,
identifies new and gone developers, and exports enriched CSV.
"""

import logging
import sys
import os
from datetime import datetime
from config import LOG_LEVEL, PARENT_OUTPUT_DIR, OUTPUT_DIR, DELTA_OUTPUT_DIR
from azure_client import AzureGraphClient
from delta_processor import DeltaProcessor
from delta_exporter import DeltaExporter

# Setup logging
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def load_inventory_csv(filename: str = None) -> dict:
    """
    Load developer inventory CSV from parent directory.

    Args:
        filename: CSV filename (uses latest YYYY-MM format if not provided)

    Returns:
        Dictionary of developers
    """
    import csv

    # If no filename, find latest YYYY-MM-developers.csv
    if not filename:
        parent_dir = os.path.join(os.path.dirname(__file__), PARENT_OUTPUT_DIR, "output")
        if not os.path.exists(parent_dir):
            logger.error(f"Output directory not found: {parent_dir}")
            return {}

        # Find latest developers CSV
        csv_files = [f for f in os.listdir(parent_dir) if f.endswith("-developers.csv") and not f.endswith("-enriched.csv")]
        if not csv_files:
            logger.error("No developer inventory CSV found in output directory")
            return {}

        # Sort by date (latest first)
        csv_files.sort(reverse=True)
        filename = os.path.join(parent_dir, csv_files[0])
        logger.info(f"Using latest inventory: {csv_files[0]}")
    else:
        parent_dir = os.path.join(os.path.dirname(__file__), PARENT_OUTPUT_DIR, "output")
        filename = os.path.join(parent_dir, filename)

    developers = {}

    try:
        with open(filename, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                dev_name = row.get("developer")
                if dev_name:
                    developers[dev_name] = dict(row)

        logger.info(f"Loaded {len(developers)} developers from {os.path.basename(filename)}")
        return developers

    except IOError as e:
        logger.error(f"Failed to load inventory CSV: {e}")
        return {}


def main():
    """Main entry point for delta tracker."""
    logger.info("Starting Delta Tracker")
    logger.info("Enriching developer inventory with Azure AD manager information")

    # Ensure output directories
    DeltaExporter.ensure_output_dirs()

    # Load developer inventory
    developers = load_inventory_csv()
    if not developers:
        logger.error("No developer inventory loaded")
        return

    # Initialize Azure client
    try:
        azure_client = AzureGraphClient()
    except Exception as e:
        logger.error(f"Failed to initialize Azure client: {e}")
        logger.warning("Continuing without Azure enrichment")
        azure_client = None

    # Process deltas and enrich data
    processor = DeltaProcessor(azure_client) if azure_client else DeltaProcessor(None)

    # Identify new developers
    new_devs = processor.identify_new_developers(developers)
    logger.info(f"Identified {len(new_devs)} new developers")

    # Identify gone developers
    gone_devs = processor.identify_gone_developers(developers)
    logger.info(f"Identified {len(gone_devs)} gone developers")

    # Enrich all developers with manager information
    enriched_developers = processor.process_all_developers(developers)

    # Get summary
    summary = processor.get_summary(developers)
    summary["new_developers"] = len(new_devs)
    summary["gone_developers"] = len(gone_devs)
    logger.info(f"Summary: {summary}")

    # Export results
    exporter = DeltaExporter()

    # Export enriched CSV
    enriched_csv = exporter.export_enriched_csv(enriched_developers, output_dir=OUTPUT_DIR)

    # Export delta tracking
    delta_csv = exporter.export_delta_tracking(new_devs, gone_devs, summary)

    # Export summary
    summary_csv = exporter.export_summary(summary)

    logger.info("Delta tracking complete")
    logger.info(f"Enriched CSV: {enriched_csv}")
    logger.info(f"Delta tracking: {delta_csv}")
    logger.info(f"Summary: {summary_csv}")


if __name__ == "__main__":
    main()
