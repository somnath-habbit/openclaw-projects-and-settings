"""
Batch Easy Apply script - applies to READY_TO_APPLY jobs.

Usage:
    python apply_jobs_batch.py --limit 5 --dry-run
"""
import asyncio
import sys
import sqlite3
import argparse
import logging
from pathlib import Path
from datetime import datetime

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Load .env
from dotenv import load_dotenv
env_path = Path(__file__).parent.parent.parent / ".env"
if env_path.exists():
    load_dotenv(env_path)

from detached_flows.config import DB_PATH
from detached_flows.Playwright.easy_apply_bot import EasyApplyBot
from detached_flows.Playwright.browser_session import BrowserSession
from detached_flows.LoginWrapper.login_manager import ensure_logged_in

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s"
)
logger = logging.getLogger("ApplyBatch")


def get_jobs_to_apply(conn: sqlite3.Connection, limit: int) -> list[dict]:
    """
    Fetch jobs that are ready to apply.

    Criteria:
    - Status is READY_TO_APPLY
    - apply_type is 'Easy Apply'
    - Not already applied
    """
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            id,
            external_id,
            title,
            company,
            job_url,
            fit_score,
            status
        FROM jobs
        WHERE status = 'READY_TO_APPLY'
          AND apply_type = 'Easy Apply'
          AND source = 'linkedin'
        ORDER BY fit_score DESC, discovered_at DESC
        LIMIT ?
    """, (limit,))

    rows = cursor.fetchall()

    jobs = []
    for row in rows:
        jobs.append({
            "id": row[0],
            "external_id": row[1],
            "job_title": row[2],
            "company": row[3],
            "job_url": row[4],
            "fit_score": row[5],
            "status": row[6],
        })

    return jobs


def update_job_status(
    conn: sqlite3.Connection,
    job_id: int,
    status: str,
    error: str = None
):
    """Update job application status."""
    cursor = conn.cursor()

    if status == "APPLIED":
        cursor.execute("""
            UPDATE jobs
            SET status = 'APPLIED',
                last_apply_result = 'SUCCESS',
                apply_attempts = COALESCE(apply_attempts, 0) + 1,
                last_attempt_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (job_id,))
    else:
        cursor.execute("""
            UPDATE jobs
            SET status = ?,
                last_apply_result = ?,
                apply_attempts = COALESCE(apply_attempts, 0) + 1,
                last_attempt_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (status, error or "FAILED", job_id))

    conn.commit()


async def apply_jobs_batch(
    limit: int = 5,
    dry_run: bool = False,
    debug: bool = False
):
    """
    Apply to jobs from database.

    Args:
        limit: Maximum applications to submit
        dry_run: If True, don't actually submit
        debug: Enable debug screenshots
    """
    logger.info(f"Starting Easy Apply batch (limit={limit}, dry_run={dry_run})")

    # Connect to database
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # Get jobs to apply
    jobs = get_jobs_to_apply(conn, limit)
    logger.info(f"Found {len(jobs)} jobs ready to apply")

    if not jobs:
        logger.info("No jobs to apply to")
        conn.close()
        return

    # Print job list
    logger.info("\nJobs to apply:")
    for i, job in enumerate(jobs, 1):
        score = job['fit_score'] or 0
        logger.info(f"  {i}. [{score:.2f}] {job['job_title']} @ {job['company']}")

    # Launch browser and login
    session = BrowserSession()
    await session.launch()

    try:
        # Ensure logged in
        logger.info("\nChecking LinkedIn login status...")
        logged_in = await ensure_logged_in(session)
        if not logged_in:
            logger.error("Failed to login to LinkedIn")
            conn.close()
            await session.close()
            return

        # Create bot
        bot = EasyApplyBot(session=session, debug=debug, dry_run=dry_run)

        # Apply to each job
        for i, job in enumerate(jobs, 1):
            external_id = job["external_id"]
            job_url = job["job_url"]
            job_title = job["job_title"]
            company = job["company"]

            logger.info(f"\n[{i}/{len(jobs)}] Applying: {job_title} @ {company}")
            logger.info(f"  URL: {job_url}")

            # Build job context for AI question handling
            job_context = {
                "job_title": job_title,
                "company": company,
                "external_id": external_id,
                "fit_score": job.get("fit_score"),
            }

            result = await bot.apply_to_job(
                job_url=job_url,
                external_id=external_id,
                job_context=job_context
            )

            # Update database based on result
            if not dry_run:
                if result["success"]:
                    update_job_status(conn, job["id"], "APPLIED")
                    logger.info(f"  ✅ Application submitted!")
                else:
                    # Keep READY_TO_APPLY status for retry
                    error = result.get("error", "Unknown error")
                    logger.warning(f"  ❌ Failed: {error}")
                    # Update attempt count but keep status
                    cursor = conn.cursor()
                    cursor.execute("""
                        UPDATE jobs
                        SET apply_attempts = COALESCE(apply_attempts, 0) + 1,
                            last_attempt_at = CURRENT_TIMESTAMP,
                            last_apply_result = ?,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = ?
                    """, (error, job["id"]))
                    conn.commit()
            else:
                logger.info(f"  🔍 [DRY RUN] Would apply - status: {result['status']}")

            # Delay between applications (avoid rate limiting)
            if i < len(jobs):
                delay = 30 if not dry_run else 5
                logger.info(f"  Waiting {delay}s before next application...")
                await asyncio.sleep(delay)

        # Print summary
        stats = bot.get_stats()
        logger.info("\n" + "=" * 50)
        logger.info("EASY APPLY COMPLETE")
        logger.info("=" * 50)
        logger.info(f"Attempted:  {stats['attempted']}")
        logger.info(f"Submitted:  {stats['submitted']} ✅")
        logger.info(f"Failed:     {stats['failed']} ❌")
        logger.info(f"Skipped:    {stats['skipped']}")

        if dry_run:
            logger.info("(DRY RUN - no applications actually submitted)")

    finally:
        conn.close()
        await session.close()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Apply to READY_TO_APPLY jobs using Easy Apply"
    )
    parser.add_argument(
        "--limit", "-l",
        type=int,
        default=5,
        help="Maximum applications to submit (default: 5)"
    )
    parser.add_argument(
        "--dry-run", "-n",
        action="store_true",
        help="Preview without actually submitting"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug screenshots"
    )

    args = parser.parse_args()

    asyncio.run(apply_jobs_batch(
        limit=args.limit,
        dry_run=args.dry_run,
        debug=args.debug
    ))


if __name__ == "__main__":
    main()
