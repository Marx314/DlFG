import logging
import sys
import json
import os
from datetime import datetime
from config import (
    AZURE_TENANT_ID,
    AZURE_CLIENT_ID,
    AZURE_CLIENT_SECRET,
    SCW_API_KEY,
    DATA_FILE,
    REPORT_FILE,
    WARNINGS_FILE,
    LOG_LEVEL_INT,
    OUTPUT_DIR,
)
from entra import EntraClient
from scw import SCWClient
from normalize import Normalizer
from report import ReportGenerator
from csv_exporter import CSVExporter
from models import NormalizedDataset

logging.basicConfig(
    level=LOG_LEVEL_INT,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(WARNINGS_FILE, mode='w'),
    ]
)
logger = logging.getLogger(__name__)


def _validate_credentials():
    if not AZURE_TENANT_ID or not AZURE_CLIENT_ID or not AZURE_CLIENT_SECRET:
        raise ValueError("Missing Entra ID credentials. Set: AZURE_TENANT_ID, AZURE_CLIENT_ID, AZURE_CLIENT_SECRET")
    if not SCW_API_KEY:
        raise ValueError("Missing SCW API key. Set: SCW_API_KEY")


def _fetch_entra_users():
    entra = EntraClient(AZURE_TENANT_ID, AZURE_CLIENT_ID, AZURE_CLIENT_SECRET)
    users = entra.get_all_users()
    if not users:
        raise RuntimeError("No users fetched from Entra ID")
    logger.info(f"✓ Fetched {len(users)} users from Entra ID")
    return entra, users


def _walk_manager_chains(entra, entra_users):
    chains = {}
    for i, user in enumerate(entra_users):
        user_id = user.get('id')
        if not user_id:
            continue
        if (i + 1) % 50 == 0:
            logger.debug(f"  Processed {i + 1}/{len(entra_users)} manager chains...")
        try:
            chains[user_id] = entra.walk_manager_chain(user_id)
        except Exception as e:
            logger.warning(f"Failed to walk chain for user {user_id}: {e}")
            chains[user_id] = (None, None, None, None)
    logger.info(f"✓ Manager chains walked for {len(chains)} users")
    return chains


def _fetch_scw_tags():
    scw = SCWClient(SCW_API_KEY)
    all_tags = scw.get_all_tags()
    valid = [tag for tag in all_tags if SCWClient.is_valid_batch_tag(tag.get('name', ''))]
    if not valid:
        raise RuntimeError("No SCW tags matching YYYY-MM pattern found. Cannot generate report.")
    logger.info(f"✓ Found {len(valid)} invitation batches")
    return scw, valid


def _fetch_completion_data(scw, valid_tags):
    data = {}
    for tag in valid_tags:
        tag_name = tag.get('name')
        tag_id = tag.get('id')
        try:
            data[tag_name] = scw.get_users_by_tag(tag_id)
        except Exception as e:
            logger.error(f"Failed to fetch users for tag {tag_name}: {e}")
            raise
    logger.info(f"✓ Fetched completion data for {len(valid_tags)} batches")
    return data


def _load_existing_dataset():
    if not os.path.exists(DATA_FILE):
        return None
    try:
        logger.debug(f"Loading existing dataset from {DATA_FILE}...")
        with open(DATA_FILE, 'r') as f:
            dataset = NormalizedDataset.from_json(f.read())
        logger.debug(f"Loaded existing dataset with {len(dataset.org_history)} org history rows")
        return dataset
    except Exception as e:
        logger.warning(f"Failed to load existing dataset: {e}")
        return None


def _normalize_data(entra_users, manager_chains, valid_tags, scw_users_per_tag):
    existing = _load_existing_dataset()
    normalizer = Normalizer(existing_dataset=existing)
    dataset = normalizer.normalize(entra_users, manager_chains, valid_tags, scw_users_per_tag)
    logger.info(f"✓ Dataset normalized:")
    logger.info(f"  - {len(dataset.developers)} developers")
    logger.info(f"  - {len(dataset.training_records)} training records")
    logger.info(f"  - {len(dataset.org_history)} org history rows")
    return dataset


def _write_data_file(dataset):
    with open(DATA_FILE, 'w') as f:
        f.write(dataset.to_json(indent=2))
    size_kb = len(dataset.to_json()) / 1024
    logger.info(f"✓ Data file written ({size_kb:.1f} KB)")


def _generate_and_write_report(dataset):
    html = ReportGenerator(dataset).generate_html()
    with open(REPORT_FILE, 'w') as f:
        f.write(html)
    size_kb = len(html) / 1024
    logger.info(f"✓ HTML report generated ({size_kb:.1f} KB)")


def _export_csv(dataset):
    csv_file = os.path.join(OUTPUT_DIR, 'training_dashboard.csv')
    exporter = CSVExporter(dataset)
    exporter.export_to_file(csv_file)
    logger.info(f"✓ CSV export written ({csv_file})")


def _log_completion():
    csv_file = os.path.join(OUTPUT_DIR, 'training_dashboard.csv')
    logger.info("\n" + "=" * 70)
    logger.info("✓ Pipeline completed successfully")
    logger.info("=" * 70)
    logger.info(f"\nOutputs:")
    logger.info(f"  - Data: {DATA_FILE}")
    logger.info(f"  - Report: {REPORT_FILE}")
    logger.info(f"  - CSV Export: {csv_file}")
    logger.info(f"\nNext steps:")
    logger.info(f"  1. Review the HTML report: {REPORT_FILE}")
    logger.info(f"  2. Import CSV to database or analytics tool: {csv_file}")
    logger.info(f"  3. Check warnings.log for any issues")


def _log_failure(e):
    logger.error("\n" + "=" * 70, exc_info=True)
    logger.error(f"Pipeline failed: {type(e).__name__}: {e}")
    logger.error("=" * 70)


def main():
    logger.info("=" * 70)
    logger.info("Training Compliance Pipeline Started")
    logger.info("=" * 70)

    try:
        logger.info("Step 1: Validating configuration...")
        _validate_credentials()
        logger.info("✓ Configuration valid")

        logger.info("\nStep 2: Fetching users from Entra ID...")
        entra, entra_users = _fetch_entra_users()

        logger.info("Walking manager chains...")
        manager_chains = _walk_manager_chains(entra, entra_users)

        logger.info("\nStep 3: Fetching invitation batches from SCW...")
        scw, valid_tags = _fetch_scw_tags()

        logger.info("Fetching user completion records per batch...")
        scw_users_per_tag = _fetch_completion_data(scw, valid_tags)

        logger.info("\nStep 4: Normalizing data...")
        dataset = _normalize_data(entra_users, manager_chains, valid_tags, scw_users_per_tag)

        logger.info(f"\nStep 5: Writing data file ({DATA_FILE})...")
        _write_data_file(dataset)

        logger.info(f"\nStep 6: Generating HTML report ({REPORT_FILE})...")
        _generate_and_write_report(dataset)

        logger.info("\nStep 7: Exporting to CSV...")
        _export_csv(dataset)

        _log_completion()
        return 0

    except Exception as e:
        _log_failure(e)
        return 1


if __name__ == "__main__":
    sys.exit(main())
