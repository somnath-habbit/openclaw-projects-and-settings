"""Playwright-based LinkedIn scraper — Phase 4 implementation."""
import re
import json
import asyncio
import logging
import sqlite3
from datetime import datetime

# Add project root to path for imports
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from detached_flows.Playwright.browser_session import BrowserSession
from detached_flows.LoginWrapper.login_manager import ensure_logged_in
from detached_flows.Playwright.page_utils import (
    nav_delay,
    page_load_delay,
    human_delay,
    get_accessibility_snapshot,
)
from detached_flows.ai_decision.decision_engine import DecisionEngine
from detached_flows.config import DB_PATH, SCREENSHOTS_DIR

logger = logging.getLogger("PlaywrightScraper")


class PlaywrightScraper:
    """Playwright-based LinkedIn job scraper."""

    def __init__(self, dry_run: bool = False, debug: bool = False):
        self.dry_run = dry_run
        self.debug = debug
        self.db_path = str(DB_PATH)
        self.ai_engine = DecisionEngine()

        # Ensure screenshots dir exists
        SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

    def _db_execute(
        self, query: str, params: tuple = (), fetch: bool = False
    ) -> list | None:
        """Execute a DB query and optionally fetch results."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(query, params)
        result = cur.fetchall() if fetch else None
        conn.commit()
        conn.close()
        return result

    def _job_exists(self, external_id: str) -> bool:
        """Check if a job with this external_id already exists in DB."""
        rows = self._db_execute(
            "SELECT 1 FROM jobs WHERE external_id = ?", (external_id,), fetch=True
        )
        return len(rows) > 0

    def _save_job(self, job: dict):
        """Save a job to the database."""
        if self.dry_run:
            logger.info(
                f"[DRY RUN] Would save: {job.get('title')} @ {job.get('company')} (id={job['external_id']})"
            )
            return

        self._db_execute(
            """
            INSERT OR IGNORE INTO jobs
            (external_id, source, title, company, location, status, job_url, enrich_status, discovered_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """,
            (
                job["external_id"],
                "linkedin",
                job.get("title"),
                job.get("company"),
                job.get("location"),
                "NEW",
                job.get("job_url"),
                "NEEDS_ENRICH",
            ),
        )
        logger.info(
            f"Saved: {job.get('title')} @ {job.get('company')} (id={job['external_id']})"
        )

    async def _extract_jobs_from_page(self, page, location: str) -> list[dict]:
        """Extract job listings from LinkedIn search results page."""
        # Use page.evaluate to extract job IDs and titles from DOM
        raw = await page.evaluate("""() => {
            const seen = {};
            document.querySelectorAll('a[href*="/jobs/view/"]').forEach(a => {
                const m = a.href.match(/\\/jobs\\/view\\/(\\d+)/);
                if (m && !seen[m[1]]) {
                    let title = a.textContent.trim();
                    // Clean up title (LinkedIn often adds extra text nodes)
                    if (title.length > 150) {
                        title = title.split('\\n')[0].trim();
                    }
                    seen[m[1]] = title || null;
                }
            });
            return seen;
        }""")

        jobs = []
        for jid, title in raw.items():
            # Clean title
            if title:
                title = title.replace(" with verification", "").strip()
                # Take first line if multi-line
                if "\n" in title:
                    title = title.split("\n")[0].strip()

            jobs.append(
                {
                    "external_id": jid,
                    "title": title or "Discovered Job",
                    "company": None,  # Will be enriched later by enrich_jobs.py
                    "location": location,
                    "job_url": f"https://www.linkedin.com/jobs/view/{jid}/",
                }
            )

        return jobs

    async def scrape(
        self,
        keywords: str = "Engineering Manager",
        location: str = "Bengaluru",
        limit: int = 1,
    ) -> list[dict]:
        """
        Main scrape method. Returns list of newly discovered jobs.

        Args:
            keywords: Job search keywords
            location: Location filter
            limit: Number of NEW jobs to find (not total jobs scanned)

        Returns:
            List of newly discovered job dicts
        """
        session = BrowserSession()
        new_jobs = []

        try:
            await session.launch()

            # Ensure logged in
            logged_in = await ensure_logged_in(session)
            if not logged_in:
                logger.error("Login failed. Cannot proceed with scraping.")
                return []

            # Save session after successful login
            await session.save_session()

            all_found = []
            offset = 0
            max_pages = 3  # Per scraping strategy: 2-3 pages max
            pages_checked = 0

            while len(new_jobs) < limit and pages_checked < max_pages:
                url = (
                    f"https://www.linkedin.com/jobs/search/"
                    f"?keywords={keywords.replace(' ', '%20')}"
                    f"&location={location.replace(' ', '%20')}"
                    f"&f_AL=true&start={offset}"
                )

                logger.info(f"Opening search: offset={offset}, url={url}")
                await session.page.goto(url, wait_until="networkidle", timeout=60000)
                await page_load_delay()  # 10-20s human delay

                if self.debug:
                    await session.page.screenshot(
                        path=str(SCREENSHOTS_DIR / f"pw_search_{offset}.png")
                    )

                # Scroll to trigger lazy loading
                await session.page.evaluate(
                    "() => window.scrollTo(0, document.body.scrollHeight)"
                )
                await human_delay(2, 4)
                await session.page.evaluate("() => window.scrollTo(0, 0)")
                await human_delay(2, 4)

                # Extract jobs
                page_jobs = await self._extract_jobs_from_page(session.page, location)

                if not page_jobs and self.ai_engine.available:
                    logger.info(
                        "Extraction returned 0 jobs — invoking AI decision engine"
                    )
                    action = await self.ai_engine.decide(
                        session.page,
                        goal="extract job listings from LinkedIn search page",
                    )
                    logger.info(f"AI action: {action}")
                    # We don't execute AI actions during search page scraping — just log

                logger.info(f"Found {len(page_jobs)} jobs on page (offset={offset})")

                # Filter for new jobs and save
                new_on_this_page = 0
                for job in page_jobs:
                    if job["external_id"] in {j["external_id"] for j in all_found}:
                        continue

                    all_found.append(job)

                    if not self._job_exists(job["external_id"]):
                        new_jobs.append(job)
                        self._save_job(job)
                        new_on_this_page += 1

                        if len(new_jobs) >= limit:
                            break

                logger.info(f"New jobs on this page: {new_on_this_page}")

                if len(new_jobs) >= limit:
                    break

                # Move to next page
                offset += 25
                pages_checked += 1

                # Anti-detection delay between pages
                await nav_delay()  # 3-12s

            # Save session
            await session.save_session()

            logger.info(f"Scrape complete. New jobs: {len(new_jobs)}")
            return new_jobs

        finally:
            await session.close()


async def main():
    import argparse

    parser = argparse.ArgumentParser(description="Playwright-based LinkedIn scraper")
    parser.add_argument("--keywords", default="Engineering Manager")
    parser.add_argument("--location", default="Bengaluru")
    parser.add_argument("--limit", type=int, default=1, help="Number of NEW jobs to find")
    parser.add_argument("--dry-run", action="store_true", help="Don't write to DB")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode (screenshots)")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    scraper = PlaywrightScraper(dry_run=args.dry_run, debug=args.debug)
    jobs = await scraper.scrape(
        keywords=args.keywords,
        location=args.location,
        limit=args.limit,
    )

    print(f"\n=== Scrape Results ===")
    print(f"New jobs found: {len(jobs)}")
    for j in jobs:
        print(
            f"  - [{j['external_id']}] {j['title']} @ {j.get('company', 'N/A')} ({j['job_url']})"
        )


if __name__ == "__main__":
    asyncio.run(main())
