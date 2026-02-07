#!/usr/bin/env python3
"""
Job Discovery Supervisor — Runs multiple search queries to discover jobs at scale.

Usage:
    # One-time: Discover until 500 total jobs in DB
    python3 scripts/job_discovery_supervisor.py --target 500

    # Daily mode: Discover 150 new jobs per run
    python3 scripts/job_discovery_supervisor.py --daily --batch-size 150

    # Dry run (no DB writes)
    python3 scripts/job_discovery_supervisor.py --target 500 --dry-run
"""
import sys
import asyncio
import sqlite3
import logging
import argparse
import random
from datetime import datetime
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from detached_flows.config import DB_PATH
from detached_flows.Playwright.linkedin_scraper import PlaywrightScraper

logger = logging.getLogger("DiscoverySupervisor")

# Search queries — diversified for Engineering Manager profile
# Each tuple: (keywords, location, max_pages)
SEARCH_QUERIES = [
    # Core EM roles
    ("Engineering Manager", "Bengaluru", 8),
    ("Engineering Manager", "India", 6),
    ("Engineering Manager", "Hyderabad", 6),
    ("Engineering Manager Remote", "India", 5),

    # Backend / Platform
    ("Engineering Manager Backend", "Bengaluru", 5),
    ("Engineering Manager Platform", "India", 5),
    ("Engineering Manager Microservices", "India", 4),

    # Cloud / DevOps / SRE
    ("Engineering Manager Cloud", "India", 5),
    ("Engineering Manager DevOps", "India", 5),
    ("Engineering Manager SRE", "India", 4),

    # AI / ML
    ("Engineering Manager AI", "India", 5),
    ("Engineering Manager Machine Learning", "India", 4),

    # Data
    ("Engineering Manager Data", "Bengaluru", 5),
    ("Data Engineering Manager", "India", 4),

    # Senior/Head roles
    ("Head of Engineering", "Bengaluru", 5),
    ("Head of Engineering", "India", 5),
    ("Director of Engineering", "Bengaluru", 4),
    ("Senior Engineering Manager", "India", 5),

    # Full stack
    ("Full Stack Engineering Manager", "India", 4),
    ("Software Engineering Manager", "Bengaluru", 6),
    ("Software Engineering Manager", "India", 5),
]


def get_total_jobs() -> int:
    """Get total job count from database."""
    try:
        conn = sqlite3.connect(str(DB_PATH))
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM jobs")
        count = cur.fetchone()[0]
        conn.close()
        return count
    except Exception as e:
        logger.error(f"DB error: {e}")
        return 0


def get_job_stats() -> dict:
    """Get job statistics from database."""
    try:
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("SELECT status, COUNT(*) as count FROM jobs GROUP BY status ORDER BY count DESC")
        stats = {row["status"]: row["count"] for row in cur.fetchall()}
        cur.execute("SELECT COUNT(*) FROM jobs")
        stats["total"] = cur.fetchone()[0]
        conn.close()
        return stats
    except Exception as e:
        logger.error(f"DB error: {e}")
        return {"total": 0}


async def _scrape_with_max_pages(
    scraper: PlaywrightScraper,
    keywords: str,
    location: str,
    limit: int,
    max_pages: int,
) -> list:
    """
    Run the scraper with a custom max_pages limit.
    Opens its own browser session per query to avoid stale sessions.
    """
    from detached_flows.Playwright.browser_session import BrowserSession
    from detached_flows.LoginWrapper.login_manager import ensure_logged_in
    from detached_flows.Playwright.page_utils import nav_delay, page_load_delay, human_delay

    session = BrowserSession()
    new_jobs = []

    try:
        await session.launch()

        logged_in = await ensure_logged_in(session)
        if not logged_in:
            logger.error("Login failed. Cannot proceed.")
            return []

        await session.save_session()

        all_found = []
        offset = 0
        pages_checked = 0
        consecutive_empty_pages = 0

        while len(new_jobs) < limit and pages_checked < max_pages:
            url = (
                f"https://www.linkedin.com/jobs/search/"
                f"?keywords={keywords.replace(' ', '%20')}"
                f"&location={location.replace(' ', '%20')}"
                f"&f_AL=true&start={offset}"
            )

            logger.info(f"  Page {pages_checked + 1}/{max_pages}: offset={offset}")
            await session.page.goto(url, wait_until="domcontentloaded", timeout=60000)
            await page_load_delay()

            # Scroll to trigger lazy loading
            await session.page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
            await human_delay(2, 4)
            await session.page.evaluate("() => window.scrollTo(0, 0)")
            await human_delay(2, 4)

            # Extract jobs from page
            page_jobs = await scraper._extract_jobs_from_page(session.page, location)
            logger.info(f"  Found {len(page_jobs)} jobs on page")

            if not page_jobs:
                consecutive_empty_pages += 1
                if consecutive_empty_pages >= 2:
                    logger.info("  2 consecutive empty pages, moving to next query")
                    break
            else:
                consecutive_empty_pages = 0

            # Filter new and save
            new_on_page = 0
            for job in page_jobs:
                if job["external_id"] in {j["external_id"] for j in all_found}:
                    continue

                all_found.append(job)

                if not scraper._job_exists(job["external_id"]):
                    new_jobs.append(job)
                    scraper._save_job(job)
                    new_on_page += 1

                    if len(new_jobs) >= limit:
                        break

            logger.info(f"  New on this page: {new_on_page}")

            if len(new_jobs) >= limit:
                break

            offset += 25
            pages_checked += 1
            await nav_delay()

        await session.save_session()
        logger.info(f"  Query complete. New jobs: {len(new_jobs)}")
        return new_jobs

    except Exception as e:
        logger.error(f"  Scrape error: {e}")
        return new_jobs
    finally:
        await session.close()


async def run_discovery(
    target: int = 500,
    batch_size: int = 150,
    daily_mode: bool = False,
    dry_run: bool = False,
    debug: bool = False,
    max_pages_override: int = None,
):
    """
    Run job discovery with multiple search queries.

    Args:
        target: Total jobs to have in DB (used in target mode)
        batch_size: Number of NEW jobs to find per run (used in daily mode)
        daily_mode: If True, find batch_size new jobs. If False, fill up to target.
        dry_run: Don't write to DB
        debug: Enable screenshots
        max_pages_override: Override max_pages per query
    """
    start_time = datetime.now()
    initial_count = get_total_jobs()

    if daily_mode:
        jobs_needed = batch_size
        logger.info(f"=== DAILY DISCOVERY MODE: Find {batch_size} new jobs ===")
    else:
        jobs_needed = max(0, target - initial_count)
        logger.info(f"=== TARGET MODE: {initial_count}/{target} jobs in DB, need {jobs_needed} more ===")

    if jobs_needed <= 0:
        logger.info(f"Target already reached! {initial_count} jobs in DB.")
        return

    total_new = 0
    queries_run = 0
    consecutive_empty = 0
    max_consecutive_empty = 5

    # Shuffle queries to vary LinkedIn access patterns
    queries = list(SEARCH_QUERIES)
    random.shuffle(queries)

    scraper = PlaywrightScraper(dry_run=dry_run, debug=debug)

    for keywords, location, default_max_pages in queries:
        if total_new >= jobs_needed:
            logger.info(f"Target reached: {total_new} new jobs found")
            break

        if consecutive_empty >= max_consecutive_empty:
            logger.warning(f"Stopping: {max_consecutive_empty} consecutive queries with 0 new jobs")
            break

        remaining = jobs_needed - total_new
        max_pages = max_pages_override or default_max_pages
        per_query_limit = min(remaining, max_pages * 25)

        logger.info(f"\n{'='*60}")
        logger.info(f"Query {queries_run + 1}: '{keywords}' in '{location}' (limit={per_query_limit})")
        logger.info(f"Progress: {total_new}/{jobs_needed} new jobs found")
        logger.info(f"{'='*60}")

        try:
            new_jobs = await _scrape_with_max_pages(
                scraper, keywords, location, per_query_limit, max_pages
            )

            new_count = len(new_jobs)
            total_new += new_count
            queries_run += 1

            if new_count > 0:
                consecutive_empty = 0
                logger.info(f"Found {new_count} new jobs for '{keywords}' in '{location}'")
            else:
                consecutive_empty += 1
                logger.info(f"No new jobs for '{keywords}' ({consecutive_empty}/{max_consecutive_empty} empty)")

            # Anti-detection: random delay between queries (15-45s)
            if total_new < jobs_needed:
                delay = random.uniform(15, 45)
                logger.info(f"Waiting {delay:.0f}s before next query...")
                await asyncio.sleep(delay)

        except Exception as e:
            logger.error(f"Error running query '{keywords}': {e}")
            consecutive_empty += 1
            await asyncio.sleep(30)
            continue

    # Final report
    elapsed = datetime.now() - start_time
    final_count = get_total_jobs()
    stats = get_job_stats()

    logger.info(f"\n{'='*60}")
    logger.info(f"=== DISCOVERY COMPLETE ===")
    logger.info(f"{'='*60}")
    logger.info(f"Duration: {elapsed}")
    logger.info(f"Queries run: {queries_run}")
    logger.info(f"New jobs found: {total_new}")
    logger.info(f"Total jobs in DB: {final_count}")
    logger.info(f"Job status breakdown:")
    for status, count in stats.items():
        if status != "total":
            logger.info(f"  {status}: {count}")
    logger.info(f"{'='*60}")


def main():
    parser = argparse.ArgumentParser(
        description="Job Discovery Supervisor - discover jobs at scale"
    )
    parser.add_argument(
        "--target", type=int, default=500,
        help="Target total jobs in database (default: 500)"
    )
    parser.add_argument(
        "--batch-size", type=int, default=150,
        help="Number of new jobs per daily run (default: 150)"
    )
    parser.add_argument(
        "--daily", action="store_true",
        help="Daily mode: find --batch-size new jobs regardless of total"
    )
    parser.add_argument(
        "--max-pages", type=int, default=None,
        help="Override max pages per query"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Don't write to database"
    )
    parser.add_argument(
        "--debug", action="store_true",
        help="Enable debug screenshots"
    )

    args = parser.parse_args()

    # Logging: console + file
    log_dir = PROJECT_ROOT / "data" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"supervisor_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(str(log_file)),
        ],
    )

    logger.info(f"Log file: {log_file}")

    asyncio.run(run_discovery(
        target=args.target,
        batch_size=args.batch_size,
        daily_mode=args.daily,
        dry_run=args.dry_run,
        debug=args.debug,
        max_pages_override=args.max_pages,
    ))


if __name__ == "__main__":
    main()
