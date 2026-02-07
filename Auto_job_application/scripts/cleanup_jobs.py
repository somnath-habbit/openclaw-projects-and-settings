#!/usr/bin/env python3
"""
Database cleanup utility for job management.

Operations:
- Delete INVALID jobs (404, deleted, removed)
- Delete stale NEW jobs (not enriched after N days)
- Archive CLOSED jobs (optional)
- Show database statistics

Usage:
    python scripts/cleanup_jobs.py --stats           # Show statistics
    python scripts/cleanup_jobs.py --delete-invalid  # Delete invalid jobs
    python scripts/cleanup_jobs.py --delete-stale 30 # Delete NEW jobs older than 30 days
    python scripts/cleanup_jobs.py --archive-closed  # Archive closed jobs
    python scripts/cleanup_jobs.py --all             # Run all cleanup operations
"""
import sys
import sqlite3
import argparse
import logging
from pathlib import Path
from datetime import datetime, timedelta

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Load .env
from dotenv import load_dotenv
env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    load_dotenv(env_path)

from detached_flows.config import DB_PATH

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("CleanupJobs")


def get_db_connection():
    """Get database connection with row factory."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def show_stats():
    """Show database statistics."""
    conn = get_db_connection()
    cursor = conn.cursor()

    print("\n" + "=" * 60)
    print("DATABASE STATISTICS")
    print("=" * 60)

    # Total jobs
    cursor.execute("SELECT COUNT(*) FROM jobs")
    total = cursor.fetchone()[0]
    print(f"\nTotal jobs: {total}")

    # Jobs by status
    print("\nJobs by status:")
    cursor.execute("""
        SELECT status, COUNT(*) as count
        FROM jobs
        GROUP BY status
        ORDER BY count DESC
    """)
    for row in cursor.fetchall():
        status = row["status"] or "NULL"
        print(f"  {status}: {row['count']}")

    # Jobs by enrich_status
    print("\nJobs by enrich_status:")
    cursor.execute("""
        SELECT enrich_status, COUNT(*) as count
        FROM jobs
        GROUP BY enrich_status
        ORDER BY count DESC
    """)
    for row in cursor.fetchall():
        status = row["enrich_status"] or "NULL"
        print(f"  {status}: {row['count']}")

    # Jobs by apply_type
    print("\nJobs by apply_type:")
    cursor.execute("""
        SELECT apply_type, COUNT(*) as count
        FROM jobs
        GROUP BY apply_type
        ORDER BY count DESC
    """)
    for row in cursor.fetchall():
        apply_type = row["apply_type"] or "NULL"
        print(f"  {apply_type}: {row['count']}")

    # Stale jobs (NEW status, older than 7 days)
    cursor.execute("""
        SELECT COUNT(*) FROM jobs
        WHERE status = 'NEW'
        AND discovered_at < datetime('now', '-7 days')
    """)
    stale_7d = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COUNT(*) FROM jobs
        WHERE status = 'NEW'
        AND discovered_at < datetime('now', '-30 days')
    """)
    stale_30d = cursor.fetchone()[0]

    print(f"\nStale NEW jobs (>7 days old): {stale_7d}")
    print(f"Stale NEW jobs (>30 days old): {stale_30d}")

    # Jobs with errors
    cursor.execute("""
        SELECT COUNT(*) FROM jobs
        WHERE last_enrich_error IS NOT NULL AND last_enrich_error != ''
    """)
    with_errors = cursor.fetchone()[0]
    print(f"Jobs with enrichment errors: {with_errors}")

    conn.close()
    print("\n" + "=" * 60)


def delete_invalid_jobs(dry_run: bool = False):
    """Delete jobs marked as INVALID."""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Find invalid jobs
    cursor.execute("""
        SELECT id, external_id, title, company, last_enrich_error
        FROM jobs
        WHERE enrich_status = 'INVALID' OR status = 'INVALID'
    """)
    invalid_jobs = cursor.fetchall()

    if not invalid_jobs:
        logger.info("No invalid jobs found")
        conn.close()
        return 0

    logger.info(f"Found {len(invalid_jobs)} invalid jobs")

    for job in invalid_jobs:
        logger.info(f"  - {job['external_id']}: {job['title']} @ {job['company']} ({job['last_enrich_error']})")

    if dry_run:
        logger.info("DRY RUN - no changes made")
        conn.close()
        return len(invalid_jobs)

    # Delete invalid jobs
    cursor.execute("""
        DELETE FROM jobs
        WHERE enrich_status = 'INVALID' OR status = 'INVALID'
    """)
    deleted = cursor.rowcount
    conn.commit()
    conn.close()

    logger.info(f"Deleted {deleted} invalid jobs")
    return deleted


def delete_stale_jobs(days: int = 30, dry_run: bool = False):
    """Delete jobs that have been NEW for too long."""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Find stale jobs
    cursor.execute("""
        SELECT id, external_id, title, company, discovered_at
        FROM jobs
        WHERE status = 'NEW'
        AND discovered_at < datetime('now', ? || ' days')
    """, (f"-{days}",))
    stale_jobs = cursor.fetchall()

    if not stale_jobs:
        logger.info(f"No stale NEW jobs older than {days} days found")
        conn.close()
        return 0

    logger.info(f"Found {len(stale_jobs)} stale jobs (older than {days} days)")

    for job in stale_jobs:
        logger.info(f"  - {job['external_id']}: {job['title']} @ {job['company']} (discovered: {job['discovered_at']})")

    if dry_run:
        logger.info("DRY RUN - no changes made")
        conn.close()
        return len(stale_jobs)

    # Delete stale jobs
    cursor.execute("""
        DELETE FROM jobs
        WHERE status = 'NEW'
        AND discovered_at < datetime('now', ? || ' days')
    """, (f"-{days}",))
    deleted = cursor.rowcount
    conn.commit()
    conn.close()

    logger.info(f"Deleted {deleted} stale jobs")
    return deleted


def archive_closed_jobs(dry_run: bool = False):
    """Archive CLOSED jobs (mark them but keep in DB)."""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Ensure archive column exists
    cursor.execute("PRAGMA table_info(jobs)")
    columns = [col[1] for col in cursor.fetchall()]
    if "is_archived" not in columns:
        cursor.execute("ALTER TABLE jobs ADD COLUMN is_archived BOOLEAN DEFAULT FALSE")
        conn.commit()
        logger.info("Added is_archived column to jobs table")

    # Find closed jobs that aren't archived
    cursor.execute("""
        SELECT id, external_id, title, company
        FROM jobs
        WHERE (status = 'CLOSED' OR enrich_status = 'CLOSED')
        AND (is_archived IS NULL OR is_archived = FALSE)
    """)
    closed_jobs = cursor.fetchall()

    if not closed_jobs:
        logger.info("No closed jobs to archive")
        conn.close()
        return 0

    logger.info(f"Found {len(closed_jobs)} closed jobs to archive")

    for job in closed_jobs:
        logger.info(f"  - {job['external_id']}: {job['title']} @ {job['company']}")

    if dry_run:
        logger.info("DRY RUN - no changes made")
        conn.close()
        return len(closed_jobs)

    # Archive closed jobs
    cursor.execute("""
        UPDATE jobs
        SET is_archived = TRUE,
            updated_at = CURRENT_TIMESTAMP
        WHERE (status = 'CLOSED' OR enrich_status = 'CLOSED')
        AND (is_archived IS NULL OR is_archived = FALSE)
    """)
    archived = cursor.rowcount
    conn.commit()
    conn.close()

    logger.info(f"Archived {archived} closed jobs")
    return archived


def delete_low_fit_jobs(threshold: float = 0.3, dry_run: bool = False):
    """Delete jobs with very low fit scores."""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Find low fit jobs
    cursor.execute("""
        SELECT id, external_id, title, company, fit_score
        FROM jobs
        WHERE fit_score IS NOT NULL AND fit_score < ?
    """, (threshold,))
    low_fit_jobs = cursor.fetchall()

    if not low_fit_jobs:
        logger.info(f"No jobs with fit_score < {threshold} found")
        conn.close()
        return 0

    logger.info(f"Found {len(low_fit_jobs)} low-fit jobs (score < {threshold})")

    for job in low_fit_jobs:
        logger.info(f"  - {job['external_id']}: {job['title']} @ {job['company']} (score: {job['fit_score']:.2f})")

    if dry_run:
        logger.info("DRY RUN - no changes made")
        conn.close()
        return len(low_fit_jobs)

    # Delete low fit jobs
    cursor.execute("""
        DELETE FROM jobs
        WHERE fit_score IS NOT NULL AND fit_score < ?
    """, (threshold,))
    deleted = cursor.rowcount
    conn.commit()
    conn.close()

    logger.info(f"Deleted {deleted} low-fit jobs")
    return deleted


def run_all_cleanup(days: int = 30, dry_run: bool = False):
    """Run all cleanup operations."""
    logger.info("Running all cleanup operations...")

    total_deleted = 0
    total_archived = 0

    # Delete invalid jobs
    logger.info("\n--- Deleting invalid jobs ---")
    total_deleted += delete_invalid_jobs(dry_run)

    # Delete stale jobs
    logger.info(f"\n--- Deleting stale jobs (>{days} days) ---")
    total_deleted += delete_stale_jobs(days, dry_run)

    # Archive closed jobs
    logger.info("\n--- Archiving closed jobs ---")
    total_archived += archive_closed_jobs(dry_run)

    logger.info("\n" + "=" * 40)
    logger.info(f"CLEANUP SUMMARY")
    logger.info("=" * 40)
    logger.info(f"Total deleted: {total_deleted}")
    logger.info(f"Total archived: {total_archived}")

    if dry_run:
        logger.info("(DRY RUN - no actual changes made)")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Database cleanup utility for job management"
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Show database statistics"
    )
    parser.add_argument(
        "--delete-invalid",
        action="store_true",
        help="Delete jobs marked as INVALID"
    )
    parser.add_argument(
        "--delete-stale",
        type=int,
        metavar="DAYS",
        help="Delete NEW jobs older than DAYS days"
    )
    parser.add_argument(
        "--archive-closed",
        action="store_true",
        help="Archive CLOSED jobs"
    )
    parser.add_argument(
        "--delete-low-fit",
        type=float,
        metavar="THRESHOLD",
        help="Delete jobs with fit_score below THRESHOLD"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Run all cleanup operations (invalid, stale 30d, archive)"
    )
    parser.add_argument(
        "--dry-run", "-n",
        action="store_true",
        help="Preview changes without modifying database"
    )

    args = parser.parse_args()

    # Default to showing stats if no operation specified
    if not any([args.stats, args.delete_invalid, args.delete_stale,
                args.archive_closed, args.delete_low_fit, args.all]):
        args.stats = True

    if args.stats:
        show_stats()

    if args.all:
        run_all_cleanup(days=30, dry_run=args.dry_run)
    else:
        if args.delete_invalid:
            delete_invalid_jobs(dry_run=args.dry_run)

        if args.delete_stale:
            delete_stale_jobs(days=args.delete_stale, dry_run=args.dry_run)

        if args.archive_closed:
            archive_closed_jobs(dry_run=args.dry_run)

        if args.delete_low_fit:
            delete_low_fit_jobs(threshold=args.delete_low_fit, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
