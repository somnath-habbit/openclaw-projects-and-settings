"""
Base External Scraper - Common logic for all external job site scrapers.

Provides DB operations, dedup, pagination, anti-detection delays, and
a standard scrape loop. Subclasses implement site-specific extraction.

Usage:
    class NaukriScraper(BaseExternalScraper):
        SITE_NAME = "naukri"
        async def _extract_jobs_from_page(self, page) -> list[dict]: ...
        def _build_search_url(self, keywords, location, offset) -> str: ...
"""
import asyncio
import logging
import sqlite3
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path

from detached_flows.Playwright.browser_session import BrowserSession
from detached_flows.Playwright.page_utils import human_delay, nav_delay, page_load_delay
from detached_flows.config import DB_PATH, SCREENSHOTS_DIR
from detached_flows.site_registry import SiteRegistry

logger = logging.getLogger("BaseExternalScraper")


class BaseExternalScraper(ABC):
    """
    Base class for all external job site scrapers.

    Subclasses must set SITE_NAME and implement:
        - _extract_jobs_from_page(page) -> list[dict]
        - _build_search_url(keywords, location, offset) -> str
    """

    SITE_NAME = ""  # Override in subclass
    MAX_PAGES = 5   # Max search result pages to scan
    RESULTS_PER_PAGE = 20  # Typical results per page

    def __init__(
        self,
        session: BrowserSession = None,
        dry_run: bool = False,
        debug: bool = False,
    ):
        self.session = session
        self._owns_session = session is None
        self.dry_run = dry_run
        self.debug = debug
        self.db_path = str(DB_PATH)
        self.site_registry = SiteRegistry()

        SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

    # ── DB Operations ──────────────────────────────────────────────────

    def _db_execute(self, query: str, params: tuple = (), fetch: bool = False):
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
        """Save a job to the database with source and apply metadata."""
        if self.dry_run:
            logger.info(
                f"[DRY RUN] Would save: {job.get('title')} @ {job.get('company')} "
                f"(id={job.get('external_id')})"
            )
            return

        self._db_execute(
            """
            INSERT OR IGNORE INTO jobs
            (external_id, source, title, company, location, status, job_url,
             apply_url, site_apply_method, enrich_status, discovered_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (
                job["external_id"],
                self.SITE_NAME,
                job.get("title"),
                job.get("company"),
                job.get("location"),
                "NEW",
                job.get("job_url"),
                job.get("apply_url", ""),
                job.get("site_apply_method", "external_form"),
                "NEEDS_ENRICH",
            ),
        )
        logger.info(
            f"Saved: {job.get('title')} @ {job.get('company')} "
            f"(id={job.get('external_id')}, source={self.SITE_NAME})"
        )

    def _record_scan(self, keywords: str, location: str, limit: int,
                     found: int, new: int, status: str):
        """Record a scan in the scans table."""
        try:
            self._db_execute(
                """
                INSERT INTO scans (job_title, location, limit_requested, found_count, new_count, status)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (f"[{self.SITE_NAME}] {keywords}", location, limit, found, new, status),
            )
        except Exception as e:
            logger.warning(f"Failed to record scan: {e}")

    # ── Login Support ──────────────────────────────────────────────────

    async def _ensure_logged_in(self, page) -> bool:
        """
        Ensure logged in to the site using LoginEngine.

        Returns True if logged in, False if login failed.
        """
        try:
            from detached_flows.registration.login_engine import LoginEngine
            from detached_flows.LoginWrapper.cred_manager import CredentialManager
            from detached_flows.config import PROFILE_PATH
            import json

            with open(PROFILE_PATH) as f:
                profile = json.load(f)

            engine = LoginEngine(
                session=self.session,
                profile=profile,
                cred_manager=CredentialManager(),
                site_registry=self.site_registry,
            )

            return await engine.ensure_logged_in(self.SITE_NAME)

        except Exception as e:
            logger.error(f"Login check failed for {self.SITE_NAME}: {e}")
            return False

    # ── Abstract Methods ───────────────────────────────────────────────

    @abstractmethod
    async def _extract_jobs_from_page(self, page) -> list[dict]:
        """
        Extract job listings from the current search results page.

        Must return list of dicts with at minimum:
            - external_id: str (unique job ID from the site)
            - title: str
            - company: str (or None)
            - location: str (or None)
            - job_url: str (full URL to job page)
            - apply_url: str (direct apply URL, if different from job_url)
            - site_apply_method: str ("external_form" or "redirect")
        """
        ...

    @abstractmethod
    def _build_search_url(self, keywords: str, location: str, offset: int) -> str:
        """
        Build the search URL for a given page offset.

        Args:
            keywords: Job search keywords
            location: Location filter
            offset: Page offset (0-indexed, multiplied by RESULTS_PER_PAGE)

        Returns:
            Full search URL string
        """
        ...

    # ── Optional Overrides ─────────────────────────────────────────────

    async def _scroll_for_lazy_load(self, page):
        """Scroll page to trigger lazy-loaded content. Override if needed."""
        await page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
        await human_delay(2, 4)
        await page.evaluate("() => window.scrollTo(0, 0)")
        await human_delay(1, 2)

    async def _handle_popups(self, page):
        """Dismiss any popups/modals that might block content. Override if needed."""
        pass

    def _requires_login(self) -> bool:
        """Whether this site requires login to search. Override if needed."""
        return True

    # ── Main Scrape Loop ───────────────────────────────────────────────

    async def scrape(
        self,
        keywords: str = "Engineering Manager",
        location: str = "Bengaluru",
        limit: int = 10,
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
        scraper_logger = logging.getLogger(f"{self.SITE_NAME.capitalize()}Scraper")

        # Create session if not provided
        if self._owns_session:
            self.session = BrowserSession()

        new_jobs = []
        all_found_ids = set()

        try:
            if self._owns_session:
                await self.session.launch()
                scraper_logger.info("Browser launched")

            page = self.session.page

            # Login if required
            if self._requires_login():
                logged_in = await self._ensure_logged_in(page)
                if not logged_in:
                    scraper_logger.error(f"Login failed for {self.SITE_NAME}. Cannot scrape.")
                    self._record_scan(keywords, location, limit, 0, 0, "LOGIN_FAILED")
                    return []
                await self.session.save_session()

            pages_checked = 0
            total_found = 0
            consecutive_empty = 0

            while len(new_jobs) < limit and pages_checked < self.MAX_PAGES:
                offset = pages_checked * self.RESULTS_PER_PAGE
                url = self._build_search_url(keywords, location, offset)

                scraper_logger.info(
                    f"Searching page {pages_checked + 1}/{self.MAX_PAGES}: offset={offset}"
                )

                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=45000)
                    await human_delay(3, 6)
                except Exception as e:
                    scraper_logger.error(f"Failed to load search page: {e}")
                    break

                # Handle any popups
                await self._handle_popups(page)

                # Scroll to trigger lazy loading
                await self._scroll_for_lazy_load(page)

                if self.debug:
                    ss_path = SCREENSHOTS_DIR / f"{self.SITE_NAME}_search_{offset}.png"
                    await page.screenshot(path=str(ss_path))

                # Extract jobs
                page_jobs = await self._extract_jobs_from_page(page)
                scraper_logger.info(f"Found {len(page_jobs)} jobs on page {pages_checked + 1}")

                if not page_jobs:
                    consecutive_empty += 1
                    if consecutive_empty >= 2:
                        scraper_logger.info("Two consecutive empty pages - stopping")
                        break
                else:
                    consecutive_empty = 0

                # Filter and save new jobs
                new_on_this_page = 0
                for job in page_jobs:
                    ext_id = job.get("external_id", "")
                    if not ext_id or ext_id in all_found_ids:
                        continue

                    all_found_ids.add(ext_id)
                    total_found += 1

                    if not self._job_exists(ext_id):
                        new_jobs.append(job)
                        self._save_job(job)
                        new_on_this_page += 1

                        if len(new_jobs) >= limit:
                            break

                scraper_logger.info(f"New jobs on this page: {new_on_this_page}")

                if len(new_jobs) >= limit:
                    break

                pages_checked += 1

                # Anti-detection delay between pages
                await nav_delay()

            # Save session
            await self.session.save_session()

            self._record_scan(keywords, location, limit, total_found, len(new_jobs), "COMPLETE")
            scraper_logger.info(
                f"Scrape complete. Total found: {total_found}, New: {len(new_jobs)}"
            )
            return new_jobs

        except Exception as e:
            scraper_logger.error(f"Scrape failed: {e}", exc_info=True)
            self._record_scan(keywords, location, limit, 0, len(new_jobs), f"ERROR: {e}")
            return new_jobs

        finally:
            if self._owns_session and self.session:
                await self.session.close()
                scraper_logger.info("Browser closed")
