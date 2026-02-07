"""
Batch AI screening script for enriched jobs.

Runs AI fitness scoring on jobs that have been enriched but not yet screened.
Updates database with fit_score, fit_reasoning, and status.

Usage:
    python screen_jobs_batch.py --limit 20 --threshold 0.6
    python screen_jobs_batch.py --dry-run  # Preview without updating DB
"""
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

from detached_flows.config import DB_PATH, PROFILE_PATH
from detached_flows.ai_decision.job_screener import JobScreener

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s"
)
logger = logging.getLogger("AIScreening")


def get_jobs_to_screen(conn: sqlite3.Connection, limit: int) -> list[dict]:
    """
    Fetch enriched jobs that need AI screening.

    Criteria:
    - Has about_job (enriched)
    - fit_score is NULL (not yet screened)
    - Status is READY_TO_APPLY or ENRICHED (not SKIPPED, CLOSED, etc.)
    """
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            id,
            external_id,
            title,
            company,
            location,
            about_job,
            about_company,
            compensation,
            work_mode,
            apply_type,
            status,
            job_url
        FROM jobs
        WHERE source = 'linkedin'
          AND about_job IS NOT NULL
          AND about_job != ''
          AND fit_score IS NULL
          AND status IN ('READY_TO_APPLY', 'ENRICHED', 'NEW')
        ORDER BY discovered_at DESC
        LIMIT ?
    """, (limit,))

    rows = cursor.fetchall()

    # Convert to dict format expected by JobScreener
    jobs = []
    for row in rows:
        jobs.append({
            "id": row[0],
            "external_id": row[1],
            "job_title": row[2],
            "company": row[3],
            "location": row[4],
            "about_job": row[5],
            "about_company": row[6],
            "compensation": row[7],
            "work_mode": row[8],
            "apply_type": row[9],
            "status": row[10],
            "job_url": row[11],
        })

    return jobs


def update_job_score(
    conn: sqlite3.Connection,
    job_id: int,
    fit_score: float,
    fit_reasoning: str,
    new_status: str
):
    """Update job with AI screening results."""
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE jobs
        SET fit_score = ?,
            fit_reasoning = ?,
            status = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
    """, (fit_score, fit_reasoning, new_status, job_id))

    conn.commit()


def determine_status(fit_score: float, threshold: float) -> str:
    """
    Determine job status based on fit score.

    Score ranges:
    - 0.8-1.0: READY_TO_APPLY (high priority)
    - threshold-0.79: READY_TO_APPLY (good fit)
    - 0.4-(threshold-0.01): REVIEW (manual review)
    - 0.0-0.39: LOW_FIT (skip)
    """
    if fit_score >= threshold:
        return "READY_TO_APPLY"
    elif fit_score >= 0.4:
        return "REVIEW"
    else:
        return "LOW_FIT"


def screen_jobs_batch(
    limit: int = 20,
    threshold: float = 0.6,
    dry_run: bool = False,
    verbose: bool = False
):
    """
    Run AI screening on enriched jobs.

    Args:
        limit: Maximum jobs to screen
        threshold: Minimum score for READY_TO_APPLY (default 0.6)
        dry_run: If True, don't update database
        verbose: If True, show detailed output
    """
    logger.info(f"Starting AI screening (limit={limit}, threshold={threshold}, dry_run={dry_run})")

    # Connect to database
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # Get jobs to screen
    jobs = get_jobs_to_screen(conn, limit)
    logger.info(f"Found {len(jobs)} jobs to screen")

    if not jobs:
        logger.info("No jobs need screening")
        conn.close()
        return

    # Initialize screener
    try:
        screener = JobScreener(profile_path=str(PROFILE_PATH))
        logger.info(f"AI Provider: {screener.ai_provider}, Model: {screener.ai_model}")
    except Exception as e:
        logger.error(f"Failed to initialize JobScreener: {e}")
        conn.close()
        return

    # Statistics
    stats = {
        "total": len(jobs),
        "screened": 0,
        "ready_to_apply": 0,
        "review": 0,
        "low_fit": 0,
        "errors": 0,
    }

    # Screen each job
    for i, job in enumerate(jobs, 1):
        job_title = job["job_title"] or "Unknown"
        company = job["company"] or "Unknown"
        external_id = job["external_id"]

        logger.info(f"[{i}/{len(jobs)}] Screening: {job_title} @ {company}")

        try:
            # Call AI screener
            result = screener.score_job(job)

            fit_score = result["fit_score"]
            reasoning = result["reasoning"]
            new_status = determine_status(fit_score, threshold)

            # Log result
            status_emoji = {
                "READY_TO_APPLY": "✅",
                "REVIEW": "🔶",
                "LOW_FIT": "❌"
            }.get(new_status, "?")

            logger.info(f"  {status_emoji} Score: {fit_score:.2f} -> {new_status}")

            if verbose:
                logger.info(f"  Reasoning: {reasoning[:200]}...")

            # Update database
            if not dry_run:
                update_job_score(conn, job["id"], fit_score, reasoning, new_status)

            # Update stats
            stats["screened"] += 1
            if new_status == "READY_TO_APPLY":
                stats["ready_to_apply"] += 1
            elif new_status == "REVIEW":
                stats["review"] += 1
            else:
                stats["low_fit"] += 1

        except Exception as e:
            logger.error(f"  ❌ Error screening {external_id}: {e}")
            stats["errors"] += 1

    # Close connection
    conn.close()

    # Print summary
    logger.info("=" * 50)
    logger.info("AI SCREENING COMPLETE")
    logger.info("=" * 50)
    logger.info(f"Total jobs:      {stats['total']}")
    logger.info(f"Screened:        {stats['screened']}")
    logger.info(f"Ready to Apply:  {stats['ready_to_apply']} ✅")
    logger.info(f"Needs Review:    {stats['review']} 🔶")
    logger.info(f"Low Fit:         {stats['low_fit']} ❌")
    logger.info(f"Errors:          {stats['errors']}")

    if dry_run:
        logger.info("(DRY RUN - no changes made to database)")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="AI-powered job screening for enriched jobs"
    )
    parser.add_argument(
        "--limit", "-l",
        type=int,
        default=20,
        help="Maximum number of jobs to screen (default: 20)"
    )
    parser.add_argument(
        "--threshold", "-t",
        type=float,
        default=0.6,
        help="Minimum score for READY_TO_APPLY status (default: 0.6)"
    )
    parser.add_argument(
        "--dry-run", "-n",
        action="store_true",
        help="Preview results without updating database"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show detailed reasoning output"
    )

    args = parser.parse_args()

    screen_jobs_batch(
        limit=args.limit,
        threshold=args.threshold,
        dry_run=args.dry_run,
        verbose=args.verbose
    )


if __name__ == "__main__":
    main()
