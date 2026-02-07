"""Batch job enrichment script — enriches jobs from database using Playwright."""
import asyncio
import sys
import sqlite3
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Load .env
from dotenv import load_dotenv
env_path = Path(__file__).parent.parent.parent / ".env"
if env_path.exists():
    load_dotenv(env_path)

from detached_flows.Playwright.job_enricher import JobEnricher
from detached_flows.Playwright.browser_session import BrowserSession
from detached_flows.LoginWrapper.login_manager import ensure_logged_in
from detached_flows.config import DB_PATH
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s"
)
logger = logging.getLogger("EnrichBatch")

FINAL_STATUSES = {"APPLIED", "SKIPPED", "BLOCKED", "FAILED"}
INVALID_STATUSES = {"INVALID", "CLOSED", "ALREADY_APPLIED"}


async def enrich_jobs(limit: int = 50, debug: bool = False):
    """
    Enrich jobs from database.

    Args:
        limit: Maximum number of jobs to enrich
        debug: Enable debug screenshots
    """
    # Get jobs needing enrichment
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, external_id, job_url, status, apply_type
        FROM jobs
        WHERE source = 'linkedin'
          AND (
            job_url IS NULL OR job_url = '' OR
            apply_type IS NULL OR apply_type = '' OR
            about_job IS NULL OR about_job = '' OR
            about_company IS NULL OR about_company = ''
          )
        ORDER BY discovered_at DESC
        LIMIT ?
    """, (limit,))

    jobs = cursor.fetchall()
    logger.info(f"Found {len(jobs)} jobs needing enrichment")

    if not jobs:
        logger.info("No jobs to enrich")
        conn.close()
        return

    # Launch browser and login
    session = BrowserSession()
    await session.launch()

    try:
        # Ensure logged in
        logger.info("Checking LinkedIn login status...")
        logged_in = await ensure_logged_in(session)
        if not logged_in:
            logger.error("Failed to login to LinkedIn")
            conn.close()
            await session.close()
            return

        # Create enricher
        enricher = JobEnricher(session=session, debug=debug)

        # Enrich each job
        for job in jobs:
            external_id = job["external_id"]
            job_url = job["job_url"] or f"https://www.linkedin.com/jobs/view/{external_id}/"

            logger.info(f"Enriching job {external_id}...")

            # Fetch details
            details = await enricher.enrich_job(external_id, job_url)

            # Check for invalid/deleted jobs - remove from database
            enrich_status = details.get("enrich_status", "")
            if enrich_status == "INVALID" or details.get("is_invalid"):
                cursor.execute("DELETE FROM jobs WHERE id = ?", (job["id"],))
                conn.commit()
                logger.warning(f"🗑️ Deleted invalid job {external_id}: {details.get('last_enrich_error')}")
                continue

            # Handle CLOSED jobs - mark but don't process
            if enrich_status == "CLOSED":
                cursor.execute("""
                    UPDATE jobs
                    SET status = 'CLOSED',
                        enrich_status = 'CLOSED',
                        last_enrich_error = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (details.get("last_enrich_error"), job["id"]))
                conn.commit()
                logger.info(f"🔒 Marked job {external_id} as CLOSED")
                continue

            # Handle ALREADY_APPLIED jobs
            if enrich_status == "ALREADY_APPLIED":
                cursor.execute("""
                    UPDATE jobs
                    SET status = 'ALREADY_APPLIED',
                        enrich_status = 'ALREADY_APPLIED',
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (job["id"],))
                conn.commit()
                logger.info(f"✅ Job {external_id} already applied")
                continue

            # Determine next status for valid jobs
            apply_type = details.get("apply_type") or job["apply_type"]
            next_status = job["status"]

            if job["status"] not in FINAL_STATUSES:
                if apply_type in {"Easy Apply", "Company Site", "Apply"}:
                    next_status = "READY_TO_APPLY"
                else:
                    next_status = "NEEDS_ENRICH"

            # Update database
            cursor.execute("""
                UPDATE jobs
                SET job_url = ?,
                    about_job = COALESCE(?, about_job),
                    about_company = COALESCE(?, about_company),
                    compensation = COALESCE(?, compensation),
                    work_mode = COALESCE(?, work_mode),
                    apply_type = COALESCE(?, apply_type),
                    status = ?,
                    enrich_status = COALESCE(?, enrich_status),
                    last_enrich_error = COALESCE(?, last_enrich_error),
                    enriched_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (
                job_url,
                details.get("about_job"),
                details.get("about_company"),
                details.get("compensation"),
                details.get("work_mode"),
                details.get("apply_type"),
                next_status,
                details.get("enrich_status"),
                details.get("last_enrich_error"),
                job["id"],
            ))
            conn.commit()

            logger.info(f"✓ Enriched {external_id} -> apply_type={apply_type}, status={next_status}")

            # Anti-detection delay
            await asyncio.sleep(3)

    finally:
        conn.close()
        await session.close()

    logger.info("✓ Enrichment complete")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Enrich jobs using Playwright")
    parser.add_argument("--limit", type=int, default=50, help="Max jobs to enrich")
    parser.add_argument("--debug", action="store_true", help="Enable debug screenshots")

    args = parser.parse_args()

    asyncio.run(enrich_jobs(limit=args.limit, debug=args.debug))
