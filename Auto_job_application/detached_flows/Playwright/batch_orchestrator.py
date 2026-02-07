"""
Batch Orchestrator - Applies to jobs in batches of 20, up to 200 total.

Features:
- Per-job timeout (5 min) - flags stuck jobs and moves on
- Post-batch failure analysis using AI
- Auto-applies fixes before next batch
- Background-friendly with file logging
- Tracks all results in DB and JSON report

Usage:
    python batch_orchestrator.py --total 200 --batch-size 20
    python batch_orchestrator.py --total 200 --batch-size 20 --dry-run
    python batch_orchestrator.py --total 40 --batch-size 10 --debug
"""
import asyncio
import sys
import sqlite3
import argparse
import logging
import json
import signal
import os
from pathlib import Path
from datetime import datetime
from typing import Optional

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Load .env
from dotenv import load_dotenv
env_path = Path(__file__).parent.parent.parent / ".env"
if env_path.exists():
    load_dotenv(env_path)

from detached_flows.config import DB_PATH, DATA_DIR
from detached_flows.Playwright.easy_apply_bot import EasyApplyBot
from detached_flows.Playwright.browser_session import BrowserSession
from detached_flows.LoginWrapper.login_manager import ensure_logged_in

# Log directory
LOG_DIR = DATA_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

# Report directory
REPORT_DIR = DATA_DIR / "batch_reports"
REPORT_DIR.mkdir(exist_ok=True)


def setup_logging(debug: bool = False) -> logging.Logger:
    """Configure logging to both file and console."""
    log_file = LOG_DIR / f"batch_apply_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG if debug else logging.INFO)

    # File handler - always verbose
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(name)s] %(levelname)s: %(message)s"
    ))
    root_logger.addHandler(file_handler)

    # Console handler - respects debug flag
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG if debug else logging.INFO)
    console_handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(name)s] %(levelname)s: %(message)s"
    ))
    root_logger.addHandler(console_handler)

    logger = logging.getLogger("BatchOrchestrator")
    logger.info(f"Logging to: {log_file}")
    return logger


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def get_jobs_to_apply(conn: sqlite3.Connection, limit: int) -> list[dict]:
    """Fetch READY_TO_APPLY Easy Apply jobs, ordered by fit_score."""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT
            id, external_id, title, company, job_url, fit_score, status,
            apply_attempts, last_apply_result
        FROM jobs
        WHERE status = 'READY_TO_APPLY'
          AND apply_type = 'Easy Apply'
          AND source = 'linkedin'
        ORDER BY fit_score DESC, discovered_at DESC
        LIMIT ?
    """, (limit,))

    return [
        {
            "id": r[0], "external_id": r[1], "job_title": r[2],
            "company": r[3], "job_url": r[4], "fit_score": r[5],
            "status": r[6], "apply_attempts": r[7] or 0,
            "last_apply_result": r[8],
        }
        for r in cursor.fetchall()
    ]


def update_job_applied(conn: sqlite3.Connection, job_id: int):
    """Mark job as successfully applied."""
    conn.execute("""
        UPDATE jobs
        SET status = 'APPLIED',
            last_apply_result = 'SUCCESS',
            apply_attempts = COALESCE(apply_attempts, 0) + 1,
            last_attempt_at = CURRENT_TIMESTAMP,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
    """, (job_id,))
    conn.commit()


def update_job_failed(conn: sqlite3.Connection, job_id: int, error: str,
                      status: str = "READY_TO_APPLY"):
    """Record a failed attempt. Keeps READY_TO_APPLY by default for retry."""
    conn.execute("""
        UPDATE jobs
        SET status = ?,
            last_apply_result = ?,
            apply_attempts = COALESCE(apply_attempts, 0) + 1,
            last_attempt_at = CURRENT_TIMESTAMP,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
    """, (status, error, job_id))
    conn.commit()


def flag_job_stuck(conn: sqlite3.Connection, job_id: int, reason: str):
    """Flag a job that timed out or got permanently stuck."""
    conn.execute("""
        UPDATE jobs
        SET status = 'APPLY_STUCK',
            last_apply_result = ?,
            apply_attempts = COALESCE(apply_attempts, 0) + 1,
            last_attempt_at = CURRENT_TIMESTAMP,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
    """, (reason, job_id))
    conn.commit()


# ---------------------------------------------------------------------------
# Per-job application with timeout
# ---------------------------------------------------------------------------

async def apply_single_job(
    bot: EasyApplyBot,
    job: dict,
    conn: sqlite3.Connection,
    dry_run: bool,
    timeout_seconds: int,
    logger: logging.Logger,
) -> dict:
    """
    Apply to a single job with a hard timeout.

    Returns a result dict with: job_id, external_id, success, status, error, duration_s
    """
    job_id = job["id"]
    external_id = job["external_id"]
    job_url = job["job_url"]
    start = datetime.now()

    result = {
        "job_id": job_id,
        "external_id": external_id,
        "job_title": job["job_title"],
        "company": job["company"],
        "success": False,
        "status": "PENDING",
        "error": None,
        "duration_s": 0,
        "timed_out": False,
    }

    job_context = {
        "job_title": job["job_title"],
        "company": job["company"],
        "external_id": external_id,
        "fit_score": job.get("fit_score"),
    }

    try:
        apply_result = await asyncio.wait_for(
            bot.apply_to_job(
                job_url=job_url,
                external_id=external_id,
                job_context=job_context,
            ),
            timeout=timeout_seconds,
        )

        result["success"] = apply_result["success"]
        result["status"] = apply_result["status"]
        result["error"] = apply_result.get("error")

        if not dry_run:
            if apply_result["success"]:
                update_job_applied(conn, job_id)
            else:
                update_job_failed(conn, job_id, apply_result.get("error", "FAILED"))

    except asyncio.TimeoutError:
        result["status"] = "TIMEOUT"
        result["error"] = f"Job timed out after {timeout_seconds}s"
        result["timed_out"] = True
        logger.error(f"  TIMEOUT after {timeout_seconds}s - flagging and moving on")

        if not dry_run:
            flag_job_stuck(conn, job_id, f"TIMEOUT_{timeout_seconds}s")

    except Exception as exc:
        result["status"] = "ERROR"
        result["error"] = str(exc)
        logger.error(f"  Unexpected error: {exc}")

        if not dry_run:
            update_job_failed(conn, job_id, str(exc))

    result["duration_s"] = round((datetime.now() - start).total_seconds(), 1)
    return result


# ---------------------------------------------------------------------------
# Post-batch failure analysis
# ---------------------------------------------------------------------------

def analyze_batch_failures(
    batch_results: list[dict],
    batch_num: int,
    logger: logging.Logger,
) -> dict:
    """
    Analyze failures in a completed batch and categorize them.

    Returns a diagnosis dict with failure categories and recommended actions.
    """
    failures = [r for r in batch_results if not r["success"]]
    successes = [r for r in batch_results if r["success"]]

    if not failures:
        logger.info(f"  Batch {batch_num}: All {len(successes)} jobs succeeded - no analysis needed")
        return {"action": "continue", "failures": 0}

    # Categorize failures
    categories = {}
    for f in failures:
        status = f["status"]
        categories.setdefault(status, []).append(f)

    logger.info(f"\n{'='*60}")
    logger.info(f"BATCH {batch_num} FAILURE ANALYSIS")
    logger.info(f"{'='*60}")
    logger.info(f"  Successes: {len(successes)}")
    logger.info(f"  Failures:  {len(failures)}")

    for category, jobs in categories.items():
        logger.info(f"\n  [{category}] ({len(jobs)} jobs):")
        for j in jobs:
            logger.info(f"    - {j['job_title']} @ {j['company']}: {j['error']}")

    # Determine recommended action
    diagnosis = {
        "action": "continue",
        "failures": len(failures),
        "successes": len(successes),
        "categories": {k: len(v) for k, v in categories.items()},
        "details": categories,
    }

    # If ALL jobs failed, something systemic is wrong
    if len(successes) == 0 and len(failures) >= 5:
        diagnosis["action"] = "pause"
        diagnosis["reason"] = "All jobs in batch failed - possible systemic issue"
        logger.warning(f"  ACTION: PAUSE - all {len(failures)} jobs failed")

    # If most failures are browser crashes, browser may be unstable
    crash_count = len(categories.get("BROWSER_CRASH", []))
    crash_count += len(categories.get("BROWSER_CRASH_RECOVERY_FAILED", []))
    if crash_count > len(failures) * 0.5:
        diagnosis["action"] = "restart_browser"
        diagnosis["reason"] = f"Browser instability: {crash_count}/{len(failures)} failures are browser crashes"
        logger.warning(f"  ACTION: RESTART BROWSER - {crash_count} crash failures")

    # If most failures are timeouts, increase timeout or skip slow jobs
    timeout_count = len(categories.get("TIMEOUT", []))
    if timeout_count > len(failures) * 0.5:
        diagnosis["action"] = "increase_timeout"
        diagnosis["reason"] = f"{timeout_count}/{len(failures)} failures are timeouts"
        logger.warning(f"  ACTION: May need to increase timeout - {timeout_count} timeouts")

    # If most failures are NO_EASY_APPLY, data is stale
    no_easy_count = len(categories.get("NO_EASY_APPLY", []))
    if no_easy_count > len(failures) * 0.5:
        diagnosis["action"] = "continue"
        diagnosis["reason"] = f"{no_easy_count} jobs no longer have Easy Apply - data may be stale"
        logger.info(f"  INFO: {no_easy_count} jobs lost Easy Apply (stale data)")

    logger.info(f"\n  Diagnosis: {diagnosis['action']}")
    if "reason" in diagnosis:
        logger.info(f"  Reason: {diagnosis['reason']}")
    logger.info(f"{'='*60}\n")

    return diagnosis


async def apply_batch_fixes(
    diagnosis: dict,
    session: BrowserSession,
    bot: EasyApplyBot,
    logger: logging.Logger,
) -> bool:
    """
    Apply fixes based on failure analysis before proceeding to next batch.

    Returns True if fixes were applied and we should continue, False to abort.
    """
    action = diagnosis.get("action", "continue")

    if action == "continue":
        return True

    if action == "restart_browser":
        logger.info("Applying fix: Restarting browser session...")
        try:
            await session.restart()
            # Re-login after restart
            logged_in = await ensure_logged_in(session)
            if logged_in:
                logger.info("Browser restarted and re-logged in successfully")
                return True
            else:
                logger.error("Failed to re-login after browser restart")
                return False
        except Exception as e:
            logger.error(f"Browser restart failed: {e}")
            return False

    if action == "increase_timeout":
        logger.info("Fix note: Many timeouts detected. Timeout will be increased for next batch.")
        return True

    if action == "pause":
        logger.error("Systemic failure detected - pausing batch processing")
        logger.error("Review the log file and batch report for details")
        return False

    return True


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------

async def run_batch_orchestrator(
    total: int = 200,
    batch_size: int = 20,
    dry_run: bool = False,
    debug: bool = False,
    job_timeout: int = 300,
    logger: Optional[logging.Logger] = None,
):
    """
    Main batch orchestrator.

    Args:
        total: Maximum total jobs to apply to (default 200)
        batch_size: Jobs per batch (default 20)
        dry_run: Don't actually submit applications
        debug: Enable debug screenshots
        job_timeout: Per-job timeout in seconds (default 300 = 5 min)
        logger: Logger instance
    """
    if logger is None:
        logger = logging.getLogger("BatchOrchestrator")

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_file = REPORT_DIR / f"batch_report_{run_id}.json"
    pid_file = LOG_DIR / "batch_orchestrator.pid"

    # Write PID for background management
    pid_file.write_text(str(os.getpid()))

    logger.info(f"{'='*60}")
    logger.info(f"BATCH ORCHESTRATOR STARTED")
    logger.info(f"{'='*60}")
    logger.info(f"  Run ID:      {run_id}")
    logger.info(f"  Total:       {total}")
    logger.info(f"  Batch size:  {batch_size}")
    logger.info(f"  Job timeout: {job_timeout}s")
    logger.info(f"  Dry run:     {dry_run}")
    logger.info(f"  Debug:       {debug}")
    logger.info(f"  PID:         {os.getpid()}")
    logger.info(f"  Report:      {report_file}")
    logger.info(f"{'='*60}\n")

    # Master report
    report = {
        "run_id": run_id,
        "started_at": datetime.now().isoformat(),
        "config": {
            "total": total, "batch_size": batch_size,
            "job_timeout": job_timeout, "dry_run": dry_run,
        },
        "batches": [],
        "summary": {
            "total_attempted": 0, "total_applied": 0,
            "total_failed": 0, "total_timed_out": 0,
            "total_skipped": 0,
        },
    }

    conn = sqlite3.connect(DB_PATH)
    session = BrowserSession()
    aborted = False

    try:
        # Launch browser
        logger.info("Launching browser...")
        await session.launch()

        # Login
        logger.info("Checking LinkedIn login...")
        logged_in = await ensure_logged_in(session)
        if not logged_in:
            logger.error("Failed to login to LinkedIn - aborting")
            return

        # Create bot
        bot = EasyApplyBot(session=session, debug=debug, dry_run=dry_run)

        # Fetch all candidate jobs upfront
        all_jobs = get_jobs_to_apply(conn, total)
        logger.info(f"Found {len(all_jobs)} jobs ready to apply (requested {total})")

        if not all_jobs:
            logger.info("No jobs to apply to - exiting")
            return

        # Process in batches
        total_processed = 0
        batch_num = 0
        current_timeout = job_timeout

        while total_processed < len(all_jobs):
            batch_num += 1
            batch_start = total_processed
            batch_end = min(total_processed + batch_size, len(all_jobs))
            batch_jobs = all_jobs[batch_start:batch_end]

            if not batch_jobs:
                break

            logger.info(f"\n{'#'*60}")
            logger.info(f"BATCH {batch_num} - Jobs {batch_start+1} to {batch_end} of {len(all_jobs)}")
            logger.info(f"{'#'*60}")

            for i, job in enumerate(batch_jobs):
                score = job.get("fit_score") or 0
                logger.info(f"  {i+1}. [{score}] {job['job_title']} @ {job['company']}")

            # Apply to each job in this batch
            batch_results = []
            for i, job in enumerate(batch_jobs):
                job_num = batch_start + i + 1
                logger.info(
                    f"\n[{job_num}/{len(all_jobs)}] "
                    f"Applying: {job['job_title']} @ {job['company']}"
                )
                logger.info(f"  URL: {job['job_url']}")

                result = await apply_single_job(
                    bot=bot,
                    job=job,
                    conn=conn,
                    dry_run=dry_run,
                    timeout_seconds=current_timeout,
                    logger=logger,
                )

                # Log result
                status_icon = "+" if result["success"] else "x"
                if result["timed_out"]:
                    status_icon = "!"
                logger.info(
                    f"  [{status_icon}] {result['status']} "
                    f"({result['duration_s']}s)"
                )
                if result["error"]:
                    logger.info(f"  Error: {result['error']}")

                batch_results.append(result)

                # Update summary
                report["summary"]["total_attempted"] += 1
                if result["success"]:
                    report["summary"]["total_applied"] += 1
                elif result["timed_out"]:
                    report["summary"]["total_timed_out"] += 1
                elif result["status"] == "NO_EASY_APPLY":
                    report["summary"]["total_skipped"] += 1
                else:
                    report["summary"]["total_failed"] += 1

                # Delay between jobs (human-like)
                if i < len(batch_jobs) - 1:
                    delay = 30 if not dry_run else 3
                    logger.info(f"  Waiting {delay}s before next job...")
                    await asyncio.sleep(delay)

            total_processed = batch_end

            # Save batch results
            batch_report = {
                "batch_num": batch_num,
                "jobs_in_batch": len(batch_jobs),
                "applied": sum(1 for r in batch_results if r["success"]),
                "failed": sum(1 for r in batch_results if not r["success"]),
                "timed_out": sum(1 for r in batch_results if r["timed_out"]),
                "results": batch_results,
            }
            report["batches"].append(batch_report)

            # Write interim report (so progress is visible)
            _save_report(report, report_file)

            # Post-batch analysis
            if total_processed < len(all_jobs):
                diagnosis = analyze_batch_failures(batch_results, batch_num, logger)

                # Adjust timeout if many timeouts
                if diagnosis.get("action") == "increase_timeout":
                    current_timeout = min(current_timeout + 120, 600)
                    logger.info(f"Increased per-job timeout to {current_timeout}s")

                # Apply fixes
                should_continue = await apply_batch_fixes(
                    diagnosis, session, bot, logger
                )

                if not should_continue:
                    logger.error(f"Aborting after batch {batch_num} due to systemic failures")
                    aborted = True
                    break

                # Cooldown between batches
                cooldown = 60 if not dry_run else 5
                logger.info(f"Batch {batch_num} complete. Cooling down {cooldown}s before next batch...")
                await asyncio.sleep(cooldown)

    except KeyboardInterrupt:
        logger.info("\nReceived interrupt signal - shutting down gracefully...")
        aborted = True

    except Exception as e:
        logger.error(f"Orchestrator error: {e}", exc_info=True)
        aborted = True

    finally:
        # Finalize report
        report["finished_at"] = datetime.now().isoformat()
        report["aborted"] = aborted
        _save_report(report, report_file)

        # Print summary
        s = report["summary"]
        logger.info(f"\n{'='*60}")
        logger.info(f"BATCH ORCHESTRATOR {'ABORTED' if aborted else 'COMPLETE'}")
        logger.info(f"{'='*60}")
        logger.info(f"  Attempted:   {s['total_attempted']}")
        logger.info(f"  Applied:     {s['total_applied']}")
        logger.info(f"  Failed:      {s['total_failed']}")
        logger.info(f"  Timed out:   {s['total_timed_out']}")
        logger.info(f"  Skipped:     {s['total_skipped']}")
        logger.info(f"  Success rate: {s['total_applied']}/{s['total_attempted']} "
                     f"({(s['total_applied']/max(s['total_attempted'],1)*100):.1f}%)")
        logger.info(f"  Report:      {report_file}")
        if dry_run:
            logger.info(f"  (DRY RUN - no applications actually submitted)")
        logger.info(f"{'='*60}")

        # Cleanup
        conn.close()
        await session.close()
        pid_file.unlink(missing_ok=True)


def _save_report(report: dict, path: Path):
    """Write report JSON atomically."""
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(report, f, indent=2, default=str)
    tmp.rename(path)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Batch job application orchestrator"
    )
    parser.add_argument(
        "--total", "-t", type=int, default=200,
        help="Maximum total jobs to apply to (default: 200)",
    )
    parser.add_argument(
        "--batch-size", "-b", type=int, default=20,
        help="Jobs per batch (default: 20)",
    )
    parser.add_argument(
        "--job-timeout", type=int, default=300,
        help="Per-job timeout in seconds (default: 300 = 5 min)",
    )
    parser.add_argument(
        "--dry-run", "-n", action="store_true",
        help="Preview without actually submitting",
    )
    parser.add_argument(
        "--debug", action="store_true",
        help="Enable debug screenshots",
    )

    args = parser.parse_args()
    logger = setup_logging(debug=args.debug)

    asyncio.run(run_batch_orchestrator(
        total=args.total,
        batch_size=args.batch_size,
        dry_run=args.dry_run,
        debug=args.debug,
        job_timeout=args.job_timeout,
        logger=logger,
    ))


if __name__ == "__main__":
    main()
