#!/usr/bin/env python3
"""Test enrichment with skip-login (assumes active session)."""
import asyncio
import sys
import sqlite3
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
env_path = Path(__file__).parent / ".env"
if env_path.exists():
    load_dotenv(env_path)

# Monkey-patch login
from detached_flows.LoginWrapper import login_manager

async def mock_login(session):
    await session.page.goto("https://www.linkedin.com", wait_until="domcontentloaded", timeout=30000)
    return True

login_manager.ensure_logged_in = mock_login

from detached_flows.Playwright.job_enricher import JobEnricher
from detached_flows.Playwright.browser_session import BrowserSession
from detached_flows.config import DB_PATH
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")

async def main():
    # Get jobs needing enrichment
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, external_id, job_url, status, apply_type
        FROM jobs
        WHERE about_job IS NULL OR about_job = ''
        LIMIT 3
    """)
    jobs = [dict(job) for job in cursor.fetchall()]

    if not jobs:
        print("No jobs need enrichment")
        return

    print(f"Testing enrichment on {len(jobs)} jobs\n")

    session = BrowserSession()
    await session.launch()

    try:
        await mock_login(session)
        print("✓ Session active\n")

        enricher = JobEnricher(session=session, debug=True)

        for job in jobs:
            external_id = job["external_id"]
            job_url = job["job_url"] or f"https://www.linkedin.com/jobs/view/{external_id}/"

            print(f"Enriching {external_id}...")
            details = await enricher.enrich_job(external_id, job_url)

            desc_len = len(details.get("about_job") or "")
            print(f"  about_job: {desc_len} chars")
            print(f"  apply_type: {details.get('apply_type')}")
            print(f"  status: {details.get('enrich_status')}")

            if desc_len > 0:
                print(f"  Preview: {details['about_job'][:200]}...")
            print()

            await asyncio.sleep(3)

    finally:
        await session.close()
        conn.close()

if __name__ == "__main__":
    asyncio.run(main())
