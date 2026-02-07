"""Playwright-based job enrichment — extracts full job details from individual pages."""
import asyncio
import logging
import re
from pathlib import Path

from detached_flows.Playwright.browser_session import BrowserSession
from detached_flows.Playwright.page_utils import human_delay, page_load_delay
from detached_flows.config import SCREENSHOTS_DIR

logger = logging.getLogger("JobEnricher")


class JobEnricher:
    """Enriches job listings with detailed information from individual job pages."""

    def __init__(self, session: BrowserSession | None = None, debug: bool = False):
        """
        Initialize enricher.

        Args:
            session: Optional BrowserSession to reuse (for batch enrichment)
            debug: Enable debug screenshots
        """
        self.session = session
        self.owns_session = session is None
        self.debug = debug

    async def __aenter__(self):
        """Context manager entry."""
        if self.owns_session:
            self.session = BrowserSession()
            await self.session.launch()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        if self.owns_session and self.session:
            await self.session.close()

    async def enrich_job(self, external_id: str, job_url: str, max_retries: int = 2) -> dict:
        """
        Fetch full job details from individual job page.

        Args:
            external_id: LinkedIn job ID
            job_url: Full URL to job page
            max_retries: Maximum retry attempts for transient failures

        Returns:
            dict with keys: about_job, about_company, compensation, work_mode, apply_type, enrich_status, last_enrich_error
        """
        if not self.session:
            raise RuntimeError("Session not initialized. Use as context manager or provide session.")

        logger.info(f"Enriching job {external_id}")

        # Retry loop for transient failures
        last_error = None
        for attempt in range(max_retries + 1):
            try:
                return await self._enrich_job_internal(external_id, job_url)
            except Exception as e:
                last_error = e
                if attempt < max_retries:
                    wait_time = (attempt + 1) * 5  # Backoff: 5s, 10s
                    logger.warning(f"Attempt {attempt + 1} failed for {external_id}: {e}. Retrying in {wait_time}s...")
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"All {max_retries + 1} attempts failed for {external_id}: {e}")

        return {
            "about_job": None,
            "about_company": None,
            "compensation": None,
            "work_mode": None,
            "apply_type": None,
            "is_closed": False,
            "already_applied": False,
            "is_invalid": False,
            "job_url": job_url,
            "enrich_status": "NEEDS_ENRICH",
            "last_enrich_error": str(last_error),
        }

    async def _enrich_job_internal(self, external_id: str, job_url: str) -> dict:
        """Internal enrichment logic (called by enrich_job with retry wrapper)."""
        try:
            # Navigate to job page (use domcontentloaded for faster, more reliable loading)
            response = await self.session.page.goto(job_url, wait_until="domcontentloaded", timeout=45000)
            await page_load_delay()

            # Check for HTTP errors (404, etc.)
            if response and response.status >= 400:
                logger.warning(f"Job {external_id} returned HTTP {response.status}")
                return {
                    "about_job": None,
                    "about_company": None,
                    "compensation": None,
                    "work_mode": None,
                    "apply_type": None,
                    "is_closed": False,
                    "already_applied": False,
                    "is_invalid": True,
                    "job_url": job_url,
                    "enrich_status": "INVALID",
                    "last_enrich_error": f"HTTP {response.status}",
                }

            # Check for invalid page indicators
            is_invalid = await self._detect_invalid_job()
            if is_invalid:
                logger.warning(f"Job {external_id} is invalid (deleted/removed)")
                return {
                    "about_job": None,
                    "about_company": None,
                    "compensation": None,
                    "work_mode": None,
                    "apply_type": None,
                    "is_closed": False,
                    "already_applied": False,
                    "is_invalid": True,
                    "job_url": job_url,
                    "enrich_status": "INVALID",
                    "last_enrich_error": "Job page invalid or deleted",
                }

            # Take initial screenshot
            if self.debug:
                screenshot_path = SCREENSHOTS_DIR / f"enrich_{external_id}_initial.png"
                await self.session.page.screenshot(path=str(screenshot_path))

            # Scroll to load lazy content
            await self._scroll_page()
            await human_delay(2, 4)

            # Expand "Show more" buttons
            await self._expand_sections()
            await human_delay(1, 2)

            # Take final screenshot
            if self.debug:
                screenshot_path = SCREENSHOTS_DIR / f"enrich_{external_id}_expanded.png"
                await self.session.page.screenshot(path=str(screenshot_path))

            # Extract all data
            details = await self._extract_job_details()

            # Check edge cases first
            if details.get("is_closed"):
                return {
                    **details,
                    "is_invalid": False,
                    "job_url": job_url,
                    "enrich_status": "CLOSED",
                    "last_enrich_error": "Job no longer accepting applications",
                }

            if details.get("already_applied"):
                return {
                    **details,
                    "is_invalid": False,
                    "job_url": job_url,
                    "enrich_status": "ALREADY_APPLIED",
                    "last_enrich_error": None,
                }

            # Assess quality
            needs_enrich, error = self._assess_quality(details)

            return {
                **details,
                "is_invalid": False,
                "job_url": job_url,
                "enrich_status": "NEEDS_ENRICH" if needs_enrich else "ENRICHED",
                "last_enrich_error": error,
            }

        except Exception as e:
            logger.error(f"Failed to enrich job {external_id}: {e}")
            raise  # Re-raise to trigger retry logic

    async def _scroll_page(self):
        """Scroll page to load lazy content."""
        await self.session.page.keyboard.press("End")
        await human_delay(1, 2)
        await self.session.page.keyboard.press("Home")
        await human_delay(1, 2)

    async def _expand_sections(self):
        """Click 'Show more' buttons to expand collapsed sections."""
        # Try to find and click "Show more" buttons
        show_more_buttons = await self.session.page.locator(
            'button:has-text("Show more"), button:has-text("See more"), button:has-text("... more")'
        ).all()

        for button in show_more_buttons[:5]:  # Limit to first 5
            try:
                if await button.is_visible():
                    await button.click()
                    await human_delay(0.5, 1)
            except Exception as e:
                logger.debug(f"Failed to click show more button: {e}")

    async def _detect_invalid_job(self) -> bool:
        """
        Check if the job page is invalid (404, deleted, removed).

        Returns:
            True if the job page appears to be invalid/deleted
        """
        invalid_indicators = await self.session.page.evaluate("""
            () => {
                const text = document.body.innerText.toLowerCase();
                const title = document.title.toLowerCase();

                // Check for explicit error messages
                const errorPhrases = [
                    'page not found',
                    '404',
                    'job not available',
                    'job no longer exists',
                    'this job has been removed',
                    'job has been deleted',
                    'link you followed may be broken',
                    'job posting was removed',
                    'we couldn\\'t find this page',
                    'this page doesn\\'t exist',
                    'sorry, this job is not available'
                ];

                // Check text content
                const hasErrorPhrase = errorPhrases.some(phrase => text.includes(phrase));

                // Check title
                const hasErrorTitle = title.includes('not found') ||
                                     title.includes('404') ||
                                     title.includes('error');

                // Check if there's a job title on the page (LinkedIn may not use h1)
                const hasJobTitle = !!document.querySelector(
                    'h1, h2, ' +
                    '.job-details-jobs-unified-top-card__job-title, ' +
                    '.jobs-unified-top-card__job-title, ' +
                    '[class*="top-card"] [class*="title"], ' +
                    '[class*="topcard"] [class*="title"]'
                ) || title.includes('|') && title.includes('linkedin');

                // Check for login redirect (not logged in)
                const isLoginPage = text.includes('sign in') && text.includes('join linkedin') && !title.includes('|');

                return {
                    hasErrorPhrase,
                    hasErrorTitle,
                    hasJobTitle,
                    isLoginPage
                };
            }
        """)

        # Job is invalid if error detected or no job title found (and not login page)
        if invalid_indicators.get("hasErrorPhrase") or invalid_indicators.get("hasErrorTitle"):
            return True

        # If no job title and not a login page, something is wrong
        if not invalid_indicators.get("hasJobTitle") and not invalid_indicators.get("isLoginPage"):
            return True

        return False

    async def _extract_job_details(self) -> dict:
        """
        Extract all job details from the page using JavaScript evaluation.

        Returns:
            dict with about_job, about_company, compensation, work_mode, apply_type
        """
        details = await self.session.page.evaluate("""
            () => {
                // IMPROVED: More robust section extraction
                function extractSection(headings) {
                    // Strategy 1: Try direct container selectors first (most reliable)
                    const directContainers = [
                        '.jobs-description__content',
                        '.job-details-jobs-unified-top-card__job-description',
                        '.jobs-description',
                        'div[class*="job-description"]',
                        'div[class*="description-content"]'
                    ];

                    for (const selector of directContainers) {
                        const container = document.querySelector(selector);
                        if (container && container.innerText && container.innerText.length > 100) {
                            // Found a container with substantial content
                            return container.innerText.trim();
                        }
                    }

                    // Strategy 2: Find by heading text and get associated content
                    for (const heading of headings) {
                        // Look for all headings
                        const allHeadings = document.querySelectorAll('h2, h3, h4, .section-title, [class*="section-header"]');

                        for (const h of allHeadings) {
                            const headingText = h.textContent.trim().toLowerCase();

                            if (headingText.includes(heading.toLowerCase())) {
                                // Found matching heading - try to get its parent container
                                let parent = h.closest('section, article, div[class*="section"], div[class*="content"]');

                                if (parent && parent.innerText && parent.innerText.length > 100) {
                                    return parent.innerText.trim();
                                }

                                // Fallback: collect all following siblings until next major heading
                                let text = '';
                                let current = h.nextElementSibling;
                                let depth = 0;

                                while (current && depth < 20) {
                                    if (current.matches('h1, h2, h3')) break;  // Stop at next heading

                                    const currentText = current.innerText || current.textContent || '';
                                    if (currentText.trim()) {
                                        text += currentText + '\\n\\n';
                                    }

                                    current = current.nextElementSibling;
                                    depth++;
                                }

                                if (text.trim().length > 100) {
                                    return text.trim();
                                }
                            }
                        }
                    }

                    // Strategy 3: Last resort - get largest text block
                    const allDivs = document.querySelectorAll('div');
                    let largestDiv = null;
                    let largestLength = 0;

                    for (const div of allDivs) {
                        const text = div.innerText || '';
                        // Check if this div has substantial direct text (not just nested content)
                        if (text.length > largestLength && text.length > 200 && text.length < 10000) {
                            largestDiv = div;
                            largestLength = text.length;
                        }
                    }

                    if (largestDiv) {
                        return largestDiv.innerText.trim();
                    }

                    return null;
                }

                // Extract apply button type
                function extractApplyType() {
                    const buttons = Array.from(document.querySelectorAll('button, a'));
                    const easyApply = buttons.find(el =>
                        el.textContent.includes('Easy Apply') ||
                        el.className.includes('easy-apply')
                    );
                    if (easyApply) return 'Easy Apply';

                    const companySite = buttons.find(el =>
                        el.textContent.match(/Apply on company|Apply on .* site/i)
                    );
                    if (companySite) return 'Company Site';

                    const apply = buttons.find(el => el.textContent.trim() === 'Apply');
                    if (apply) return 'Apply';

                    return null;
                }

                // Extract compensation
                function extractCompensation() {
                    const salaryPatterns = [
                        /\\$\\s*([\\d,]+)\\s*-\\s*\\$\\s*([\\d,]+)\\s*\\/\\s*(year|yr|hour|hr)/i,
                        /\\$\\s*([\\d,]+)\\s*\\/\\s*(year|yr|hour|hr)/i,
                        /([\\d,]+)\\s*LPA/i,
                        /₹\\s*([\\d,]+)\\s*-\\s*₹\\s*([\\d,]+)/i,
                    ];

                    const text = document.body.innerText;
                    for (const pattern of salaryPatterns) {
                        const match = text.match(pattern);
                        if (match) return match[0];
                    }
                    return null;
                }

                // Extract work mode
                function extractWorkMode() {
                    const text = document.body.innerText.toLowerCase();
                    if (text.includes('remote') || text.includes('work from home')) return 'Remote';
                    if (text.includes('hybrid')) return 'Hybrid';
                    if (text.includes('on-site') || text.includes('onsite') || text.includes('office')) return 'On-site';
                    return null;
                }

                // Detect if job is closed/no longer accepting applications
                function detectClosedJob() {
                    const text = document.body.innerText.toLowerCase();
                    const closedPhrases = [
                        'no longer accepting applications',
                        'not accepting applications',
                        'application closed',
                        'hiring paused',
                        'position filled',
                        'position is filled',
                        'applications have closed',
                        'job posting has been closed',
                        'this job is no longer available'
                    ];
                    return closedPhrases.some(phrase => text.includes(phrase));
                }

                // Detect if user has already applied
                function detectAlreadyApplied() {
                    const text = document.body.innerText.toLowerCase();
                    const appliedPhrases = [
                        'application sent',
                        'you applied',
                        'your application',
                        'view application',
                        'application submitted'
                    ];
                    return appliedPhrases.some(phrase => text.includes(phrase));
                }

                return {
                    about_job: extractSection(['About the job', 'Job description', 'Description']),
                    about_company: extractSection(['About the company', 'About us', 'Company overview']),
                    compensation: extractCompensation(),
                    work_mode: extractWorkMode(),
                    apply_type: extractApplyType(),
                    is_closed: detectClosedJob(),
                    already_applied: detectAlreadyApplied(),
                };
            }
        """)

        logger.debug(f"Extracted details: about_job={len(details.get('about_job') or '')} chars, "
                    f"apply_type={details.get('apply_type')}")

        return details

    def _assess_quality(self, details: dict) -> tuple[bool, str | None]:
        """
        Assess enrichment quality.

        Returns:
            (needs_enrich: bool, error: str | None)
        """
        if not details.get("apply_type"):
            return True, "apply_type_missing"

        about_job = details.get("about_job") or ""
        if len(about_job.strip()) < 100:
            return True, "about_job_too_short"

        return False, None


async def enrich_jobs_batch(job_ids_urls: list[tuple[str, str]], debug: bool = False) -> list[dict]:
    """
    Enrich multiple jobs in a single browser session.

    Args:
        job_ids_urls: List of (external_id, job_url) tuples
        debug: Enable debug screenshots

    Returns:
        List of enrichment result dicts
    """
    results = []

    async with JobEnricher(debug=debug) as enricher:
        for external_id, job_url in job_ids_urls:
            result = await enricher.enrich_job(external_id, job_url)
            results.append({"external_id": external_id, **result})
            await human_delay(2, 4)  # Anti-detection delay between jobs

    return results
