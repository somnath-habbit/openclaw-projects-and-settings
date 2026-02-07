"""
Instahyre Scraper - Extracts job listings from Instahyre.com.

Instahyre is an invitation-based platform where candidates see curated
opportunities after login. No public search - must be logged in to browse.
Jobs are listed at /candidate/opportunities/ as cards.

Usage:
    scraper = InstahyreScraper(dry_run=True, debug=True)
    jobs = await scraper.scrape(keywords="DevOps Engineer", location="Bengaluru", limit=10)

    # Or as CLI:
    python instahyre_scraper.py --limit 10 --dry-run
"""
import asyncio
import logging
import re

from detached_flows.Playwright.base_scraper import BaseExternalScraper
from detached_flows.Playwright.page_utils import human_delay

logger = logging.getLogger("InstahyreScraper")


class InstahyreScraper(BaseExternalScraper):
    """
    Scraper for Instahyre job opportunities.

    Instahyre is invitation-based. Login required. Jobs are listed at
    /candidate/opportunities/ - no public search page. Keywords/location
    filtering happens client-side or is not available.
    """

    SITE_NAME = "instahyre"
    MAX_PAGES = 3  # Instahyre paginates via infinite scroll / "Load More"
    RESULTS_PER_PAGE = 20

    def _build_search_url(self, keywords: str, location: str, offset: int) -> str:
        """
        Build Instahyre opportunities URL.

        Instahyre doesn't have a traditional search. All opportunities are at
        /candidate/opportunities/ with optional filters.
        """
        base = "https://www.instahyre.com/candidate/opportunities/"

        # Instahyre uses page parameter for pagination
        page_num = (offset // self.RESULTS_PER_PAGE) + 1
        if page_num > 1:
            base += f"?page={page_num}"

        return base

    async def _extract_jobs_from_page(self, page) -> list[dict]:
        """Extract job listings from Instahyre opportunities page."""
        jobs = await page.evaluate("""() => {
            const results = [];
            const seen = new Set();

            // Instahyre opportunity cards
            const cards = document.querySelectorAll(
                '.opportunity-card, [class*="opportunity"], ' +
                '.job-card, [class*="jobCard"], ' +
                'div[data-opportunity-id], div[data-id], ' +
                '.opp-listing .card, .opportunity-listing > div'
            );

            cards.forEach(card => {
                try {
                    let jobId = '';
                    let title = '';
                    let company = '';
                    let location = '';
                    let jobUrl = '';

                    // Get ID from data attributes
                    jobId = card.getAttribute('data-opportunity-id') ||
                            card.getAttribute('data-id') || '';

                    // Extract from link
                    const link = card.querySelector('a[href*="/opportunity/"], a[href*="/job/"]');
                    if (link) {
                        jobUrl = link.href || '';
                        if (!jobId) {
                            const m = jobUrl.match(/\\/(\\d+)/);
                            if (m) jobId = m[1];
                        }
                    }

                    // Generate ID from card index if none found
                    if (!jobId) {
                        const allText = card.textContent.trim().substring(0, 100);
                        jobId = btoa(allText).substring(0, 16).replace(/[^a-zA-Z0-9]/g, '');
                    }

                    if (!jobId || seen.has(jobId)) return;
                    seen.add(jobId);

                    // Extract title
                    const titleEl = card.querySelector(
                        '.opportunity-title, .job-title, h3, h4, ' +
                        '[class*="title"], [class*="designation"], ' +
                        'a[href*="/opportunity/"]'
                    );
                    title = titleEl ? titleEl.textContent.trim() : '';

                    // Extract company
                    const compEl = card.querySelector(
                        '.company-name, [class*="company"], .org-name, ' +
                        '[class*="organization"]'
                    );
                    company = compEl ? compEl.textContent.trim() : '';

                    // Extract location
                    const locEl = card.querySelector(
                        '.location, [class*="location"], [class*="city"]'
                    );
                    location = locEl ? locEl.textContent.trim() : '';

                    // Build job URL if not found
                    if (!jobUrl) {
                        jobUrl = 'https://www.instahyre.com/candidate/opportunities/';
                    }

                    if (title) {
                        results.push({
                            external_id: 'instahyre_' + jobId,
                            title: title.substring(0, 200),
                            company: company.substring(0, 200) || null,
                            location: location.substring(0, 200) || null,
                            job_url: jobUrl,
                            apply_url: jobUrl,
                            site_apply_method: 'external_form',
                        });
                    }
                } catch (e) {
                    // Skip malformed card
                }
            });

            // Fallback: look for any structured job-like content
            if (results.length === 0) {
                // Try React-rendered content (Instahyre uses React)
                const textBlocks = document.querySelectorAll('[class*="opp"] h3, [class*="opp"] h4');
                textBlocks.forEach((el, idx) => {
                    const text = el.textContent.trim();
                    if (text && text.length > 3 && text.length < 150) {
                        const id = 'instahyre_fb_' + idx;
                        if (!seen.has(id)) {
                            seen.add(id);
                            // Try to find company nearby
                            let company = null;
                            const parent = el.closest('[class*="opp"], [class*="card"]');
                            if (parent) {
                                const compEl = parent.querySelector('[class*="company"], [class*="org"]');
                                company = compEl ? compEl.textContent.trim() : null;
                            }
                            results.push({
                                external_id: id,
                                title: text,
                                company: company,
                                location: null,
                                job_url: 'https://www.instahyre.com/candidate/opportunities/',
                                apply_url: '',
                                site_apply_method: 'external_form',
                            });
                        }
                    }
                });
            }

            return results;
        }""")

        return jobs

    async def _scroll_for_lazy_load(self, page):
        """
        Instahyre uses infinite scroll or "Load More" button.
        Scroll multiple times to load more content.
        """
        for _ in range(3):
            await page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
            await human_delay(2, 4)

            # Check for "Load More" button
            try:
                load_more = page.locator(
                    'button:has-text("Load More"), button:has-text("Show More"), '
                    'a:has-text("Load More"), [class*="loadMore"]'
                ).first
                if await load_more.count() > 0 and await load_more.is_visible():
                    await load_more.click()
                    await human_delay(2, 4)
            except Exception:
                pass

        await page.evaluate("() => window.scrollTo(0, 0)")
        await human_delay(1, 2)

    async def _handle_popups(self, page):
        """Dismiss Instahyre popups/modals."""
        try:
            for sel in [
                'button[class*="close"]',
                '[class*="modal"] button[class*="close"]',
                'button:has-text("Got it")',
                'button:has-text("Dismiss")',
            ]:
                btn = page.locator(sel).first
                if await btn.count() > 0 and await btn.is_visible():
                    await btn.click()
                    await human_delay(0.5, 1)
                    break
        except Exception:
            pass

    def _requires_login(self) -> bool:
        """Instahyre requires login to see opportunities."""
        return True


async def main():
    import argparse

    parser = argparse.ArgumentParser(description="Instahyre job scraper")
    parser.add_argument("--keywords", default="Engineering Manager",
                        help="Keywords (used for filtering display, not search)")
    parser.add_argument("--location", default="Bengaluru",
                        help="Location (used for filtering display, not search)")
    parser.add_argument("--limit", type=int, default=10, help="Number of NEW jobs to find")
    parser.add_argument("--dry-run", action="store_true", help="Don't write to DB")
    parser.add_argument("--debug", action="store_true", help="Enable debug screenshots")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    scraper = InstahyreScraper(dry_run=args.dry_run, debug=args.debug)
    jobs = await scraper.scrape(
        keywords=args.keywords,
        location=args.location,
        limit=args.limit,
    )

    print(f"\n=== Instahyre Scrape Results ===")
    print(f"New jobs found: {len(jobs)}")
    for j in jobs:
        print(f"  - [{j['external_id']}] {j['title']} @ {j.get('company', 'N/A')}")
        print(f"    URL: {j['job_url']}")


if __name__ == "__main__":
    asyncio.run(main())
