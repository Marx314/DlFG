"""
Developers Security Training Inventory - Entry point.

Main orchestrator for querying GitHub and Bitbucket APIs to collect
developer activity and assess Secure Code Warrior training fit.
"""

import logging
import sys
import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Generator, Tuple

from logger_setup import setup_logging
from config import (
    LOG_LEVEL,
    DAYS_LOOKBACK,
    SINCE_DATE,
    OUTPUT_DIR,
    OUTPUT_FILENAME,
    COMMIT_CACHE_DIR,
    COMMIT_CACHE_ENABLED,
)
from github_client import GitHubClient
from bitbucket_client import BitbucketClient
from data_processor import DataProcessor
from csv_exporter import CSVExporter
from service_account_filter import ServiceAccountFilter
from checkpoint import Checkpoint
from timestamp_utils import TimestampConverter
from commit_cache import CommitCache

# Setup logging
setup_logging()
logger = logging.getLogger(__name__)


def _parse_cli_flags() -> Tuple[bool, bool, bool]:
    """Parse and remove CLI flags, returning (clear_cache, use_cache, clear_checkpoint)."""
    clear_cache = "--clear-cache" in sys.argv
    use_cache = "--no-cache" not in sys.argv
    clear_checkpoint = "--clear-checkpoint" in sys.argv

    for flag in ["--clear-cache", "--no-cache", "--clear-checkpoint"]:
        if flag in sys.argv:
            sys.argv.remove(flag)

    return clear_cache, use_cache, clear_checkpoint


def _get_scopes() -> Tuple[str, str]:
    """Get GitHub and Bitbucket scopes from env vars or CLI args."""
    github_scope = os.getenv("GITHUB_SCOPE", "")
    bitbucket_scope = os.getenv("BITBUCKET_SCOPE", "")

    if len(sys.argv) > 1:
        github_scope = sys.argv[1]
    if len(sys.argv) > 2:
        bitbucket_scope = sys.argv[2]

    return github_scope, bitbucket_scope


def _validate_scopes(github_scope: str, bitbucket_scope: str) -> bool:
    """Validate that at least one scope is provided."""
    if github_scope or bitbucket_scope:
        return True

    logger.warning("No GitHub or Bitbucket scope provided")
    logger.info("Usage:")
    logger.info("  export GITHUB_SCOPE='org-name'")
    logger.info("  export BITBUCKET_SCOPE='scope' (or omit for all projects)")
    logger.info("  python main.py [--clear-checkpoint]")
    return False


def _setup_cache(use_cache: bool, clear_cache: bool) -> CommitCache:
    """Initialize and optionally clear commit cache."""
    if not use_cache or not COMMIT_CACHE_ENABLED:
        if not use_cache:
            logger.info("Commit cache disabled - will fetch fresh data from APIs")
        return None

    commit_cache = CommitCache(cache_dir=COMMIT_CACHE_DIR, enabled=True)

    if clear_cache:
        commit_cache.clear_all()
        logger.info("Commit cache cleared - will fetch fresh data")
    else:
        cache_stats = commit_cache.get_stats()
        if cache_stats["cached_repos"] > 0:
            logger.info(
                f"Commit cache available: {cache_stats['cached_repos']} repos cached, "
                f"{cache_stats['total_cached_commits']} total commits"
            )

    return commit_cache


def _setup_checkpoint(clear_checkpoint: bool) -> Checkpoint:
    """Initialize and optionally clear checkpoint."""
    checkpoint = Checkpoint(os.path.join(OUTPUT_DIR, "checkpoint.json"))

    if clear_checkpoint:
        checkpoint.clear()
        checkpoint.save()
        logger.info("Checkpoint cleared - starting fresh")
    else:
        counts = checkpoint.get_processed_count()
        if counts["github"] > 0 or counts["bitbucket"] > 0:
            logger.info(
                f"Resuming from checkpoint: {counts['github']} GitHub repos, "
                f"{counts['bitbucket']} Bitbucket repos, {counts['developers']} developers processed"
            )

    return checkpoint


def _update_developer(
    developers: Dict,
    author_name: str,
    author_email: str,
    commit_date: str,
    repo_full_name: str,
    platform: str,
    extra_data: Dict = None,
) -> None:
    """Update developer record with commit data."""
    if author_name not in developers:
        developers[author_name] = {
            "email": author_email,
            "latest_commit_date": commit_date,
            "repositories": [],
            "repo_platforms": {repo_full_name: platform},
            "commits": 0,
            "platforms": [platform],
            **(extra_data or {}),
        }
    else:
        if commit_date > developers[author_name].get("latest_commit_date", ""):
            developers[author_name]["latest_commit_date"] = commit_date

    developers[author_name]["commits"] += 1

    if repo_full_name not in developers[author_name]["repositories"]:
        developers[author_name]["repositories"].append(repo_full_name)
        developers[author_name]["repo_platforms"][repo_full_name] = platform


def stream_github_developers(
    scope: str, checkpoint: Checkpoint, commit_cache: CommitCache = None
) -> Generator[Tuple[str, Dict, str], None, None]:
    """Stream GitHub developers from GitHub API."""
    logger.info(f"[GitHub] Starting query for scope: {scope}")

    client = GitHubClient(commit_cache=commit_cache)
    try:
        user = client.get_authenticated_user()
        logger.info(f"[GitHub] Authenticated as: {user.get('login')}")
    except Exception as e:
        logger.error(f"[GitHub] Authentication failed: {e}")
        return

    developers: Dict = {}
    skipped = 0

    for target in [t.strip() for t in scope.split(",")]:
        logger.info(f"[GitHub] Processing target: {target}")
        try:
            repos = client.get_org_repos(target) or client.get_user_repos(target)
        except Exception as e:
            logger.warning(f"[GitHub] Could not fetch repos for {target}: {e}")
            continue

        repos = client.filter_repos(repos)
        logger.info(f"[GitHub] {len(repos)} repositories for {target}")

        for repo in repos:
            owner = repo["owner"]["login"]
            repo_name = repo["name"]
            repo_full_name = f"{owner}/{repo_name}"

            if checkpoint.is_github_repo_processed(owner, repo_name):
                skipped += 1
                continue

            try:
                commits = client.get_repo_commits(owner, repo_name)

                if not commits:
                    checkpoint.mark_github_repo_processed(owner, repo_name)
                    checkpoint.save()
                    continue

                logger.info(f"[GitHub] {len(commits)} commits in {repo_full_name}")
                repo_properties = client.get_repo_properties(owner, repo_name)

                for commit in commits:
                    author = commit.get("commit", {}).get("author", {})
                    author_name = author.get("name", "unknown")
                    author_email = (author.get("email") or "unknown").lower().strip()
                    commit_date = author.get("date", "")
                    year_month = TimestampConverter.get_month_string(commit_date)

                    _update_developer(
                        developers, author_name, author_email, commit_date,
                        repo_full_name, "GitHub", {"github_properties": {}}
                    )

                    if repo_properties:
                        developers[author_name]["github_properties"][repo_full_name] = repo_properties

                    yield author_name, developers[author_name], year_month

                checkpoint.mark_github_repo_processed(owner, repo_name)
                checkpoint.save()

            except Exception as e:
                logger.warning(f"[GitHub] Error processing {repo_full_name}: {e}")

    if skipped:
        logger.info(f"[GitHub] Skipped {skipped} already-processed repos")
    logger.info(f"[GitHub] Query complete. {len(developers)} developers found.")


def stream_bitbucket_developers(
    scope: str, checkpoint: Checkpoint, commit_cache: CommitCache = None
) -> Generator[Tuple[str, Dict, str], None, None]:
    """Stream Bitbucket developers from Bitbucket Server API."""
    logger.info(f"[Bitbucket] Starting query for scope: {scope}")

    client = BitbucketClient(commit_cache=commit_cache)

    developers: Dict = {}
    skipped = 0

    try:
        projects = client.get_all_projects()
        logger.info(f"[Bitbucket] Found {len(projects)} projects")
    except Exception as e:
        logger.error(f"[Bitbucket] Could not fetch projects: {e}")
        return

    for project in projects:
        project_key = project.get("key", "")
        project_name = project.get("name", "")
        logger.info(f"[Bitbucket] Processing project: {project_key} ({project_name})")

        try:
            repos = client.get_project_repos(project_key)
        except Exception as e:
            logger.warning(f"[Bitbucket] Could not fetch repos for {project_key}: {e}")
            continue

        repos = client.filter_repos(repos)
        logger.info(f"[Bitbucket] {len(repos)} repositories in {project_key}")

        for repo in repos:
            repo_slug = repo.get("slug", "")
            repo_full_name = f"{project_key}/{repo_slug}"

            if checkpoint.is_bitbucket_repo_processed(project_key, repo_slug):
                skipped += 1
                continue

            try:
                commits = client.get_repo_commits(project_key, repo_slug)

                if not commits:
                    checkpoint.mark_bitbucket_repo_processed(project_key, repo_slug)
                    checkpoint.save()
                    continue

                logger.info(f"[Bitbucket] {len(commits)} commits in {repo_full_name}")

                for commit in commits:
                    author = commit.get("author", {})
                    author_name = author.get("name", "unknown")
                    author_email = (author.get("emailAddress") or "unknown").lower().strip()

                    commit_date = ""
                    timestamp = commit.get("authorTimestamp", 0)
                    if timestamp:
                        try:
                            commit_date = TimestampConverter.to_iso_format(timestamp)
                        except ValueError:
                            logger.debug(f"Could not convert timestamp {timestamp}")

                    year_month = TimestampConverter.get_month_string(commit_date)

                    _update_developer(
                        developers, author_name, author_email, commit_date,
                        repo_full_name, "Bitbucket", {"bitbucket_projects": set()}
                    )

                    project_ref = f"{project_key}/{project_name}"
                    developers[author_name]["bitbucket_projects"].add(project_ref)

                    yield author_name, developers[author_name], year_month

                checkpoint.mark_bitbucket_repo_processed(project_key, repo_slug)
                checkpoint.save()

            except Exception as e:
                logger.warning(f"[Bitbucket] Error processing {repo_full_name}: {e}")

    if skipped:
        logger.info(f"[Bitbucket] Skipped {skipped} already-processed repos")
    logger.info(f"[Bitbucket] Query complete. {len(developers)} developers found.")


def _create_developer_handler(
    processor: DataProcessor,
    exporter: CSVExporter,
    sa_filter: ServiceAccountFilter,
    lock: threading.Lock,
) -> callable:
    """Create a thread-safe developer handling function."""
    def handle_developer(dev_name: str, dev_data: Dict, year_month: str) -> None:
        with lock:
            processor.add_developer_data({dev_name: dev_data})

            filtered = sa_filter.filter_developers(
                {dev_name: processor.developers.get(dev_name, dev_data)}
            )
            if not filtered:
                return

            for name in filtered:
                enriched = {
                    **processor.developers[name],
                    "technology_profile": processor.calculate_technology_profile(name),
                    "training_fit_score": round(processor.calculate_training_fit_score(name), 2),
                }
                exporter.write_developer(name, enriched, year_month=year_month)

    return handle_developer


def _query_and_stream_developers(
    processor: DataProcessor,
    exporter: CSVExporter,
    github_scope: str,
    bitbucket_scope: str,
    checkpoint: Checkpoint,
    commit_cache: CommitCache = None,
) -> None:
    """Query GitHub and Bitbucket in parallel, writing to CSV."""
    lock = threading.Lock()
    sa_filter = ServiceAccountFilter()
    handle_developer = _create_developer_handler(processor, exporter, sa_filter, lock)

    def run_stream(stream_func, scope):
        for dev_name, dev_data, year_month in stream_func(scope, checkpoint, commit_cache):
            handle_developer(dev_name, dev_data, year_month)

    with ThreadPoolExecutor(max_workers=2, thread_name_prefix="platform") as pool:
        futures = []
        futures.append(pool.submit(run_stream, stream_github_developers, github_scope))
        futures.append(pool.submit(run_stream, stream_bitbucket_developers, bitbucket_scope))

        for future in as_completed(futures):
            exc = future.exception()
            if exc:
                logger.error(f"Platform query thread raised an exception: {exc}")

    total = len(processor.developers)
    checkpoint.update_developer_count(total)
    checkpoint.save()
    logger.info(f"Total unique developers (deduplicated across platforms): {total}")


def main() -> None:
    """Main entry point."""
    logger.info("Starting Developers Security Training Inventory")
    logger.info(f"Query period: last {DAYS_LOOKBACK} days (since {SINCE_DATE})")

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Parse flags and get scopes
    clear_cache, use_cache, clear_checkpoint = _parse_cli_flags()
    github_scope, bitbucket_scope = _get_scopes()

    # Validate
    if not _validate_scopes(github_scope, bitbucket_scope):
        return

    # Setup components
    commit_cache = _setup_cache(use_cache, clear_cache)
    checkpoint = _setup_checkpoint(clear_checkpoint)

    # Run inventory
    processor = DataProcessor()
    with CSVExporter() as exporter:
        exporter.open()
        _query_and_stream_developers(
            processor, exporter, github_scope, bitbucket_scope, checkpoint, commit_cache
        )

    # Export summary
    stats = processor.get_summary_stats()
    logger.info(f"Summary: {stats}")
    CSVExporter.export_summary(stats, OUTPUT_FILENAME.replace(".csv", "_summary.csv"))
    logger.info("Inventory complete")


if __name__ == "__main__":
    main()
