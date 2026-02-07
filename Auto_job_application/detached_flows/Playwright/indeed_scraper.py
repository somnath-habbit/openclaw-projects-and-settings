"""
Indeed Scraper - Extracts job listings from Indeed.com search results.

Indeed uses server-rendered HTML with job cards containing data-jk attributes
for unique job IDs. Supports keyword + location search with pagination.

Usage:
    scraper = IndeedScraper(dry_run=True, debug=True)
    jobs = await scraper.scrape(keywords="DevOps Engineer", location="Bengaluru", limit=10)

    # Or as CLI:
    python indeed_scraper.py --keywords "DevOps" --location "Bengaluru" --limit 5 --dry-run
"""
import asyncio
import logging
from urllib.parse import quote_plus

from detached_flows.Playwright.base_scraper import BaseExternalScraper
from detached_flows.Playwright.page_utils import human_delay

logger = logging.getLogger("IndeedScraper")


class IndeedScraper(BaseExternalScraper):
    """Scraper for Indeed.com / Indeed.co.in job listings."""

    SITE_NAME = "indeed"
    MAX_PAGES = 5
    RESULTS_PER_PAGE = 15  # Indeed shows ~15 results per page

    # Use India Indeed by default (configurable)
    BASE_DOMAIN = "https://www.indeed.com"

    def __init__(self, *args, india: bool = True, **kwargs):
        super().__init__(*args, **kwargs)
        if india:
            self.BASE_DOMAIN = "https://in.indeed.com"

    def _build_search_url(self, keywords: str, location: str, offset: int) -> str:
        """Build Indeed search URL with keyword, location, and page offset."""
        kw_encoded = quote_plus(keywords)
        loc_encoded = quote_plus(location)

        # Indeed uses start= for pagination (0, 10, 20, ...)
        start = offset

        url = f"{self.BASE_DOMAIN}/jobs?q={kw_encoded}&l={loc_encoded}&start={start}"
        return url

    async def _extract_jobs_from_page(self, page) -> list[dict]:
        """Extract job listings from Indeed search results page."""
        jobs = await page.evaluate("""() => {
            const results = [];
            const seen = new Set();

            // Indeed job cards have data-jk attribute with unique job key
            const cards = document.querySelectorAll(
                '[data-jk], .job_seen_beacon, .resultContent, ' +
                '.jobsearch-ResultsList .result, .tapItem'
            );

            cards.forEach(card => {
                try {
                    let jobId = '';
                    let title = '';
                    let company = '';
                    let location = '';
                    let jobUrl = '';

                    // Get job key from data-jk attribute
                    jobId = card.getAttribute('data-jk') || '';

                    // Walk up to find data-jk if not on this element
                    if (!jobId) {
                        let parent = card.parentElement;
                        for (let i = 0; i < 5 && parent; i++) {
                            jobId = parent.getAttribute('data-jk') || '';
                            if (jobId) break;
                            parent = parent.parentElement;
                        }
                    }

                    // Try extracting from link href
                    const link = card.querySelector('a[href*="jk="], a[id^="job_"], a.jcs-JobTitle');
                    if (link) {
                        const href = link.href || '';
                        if (!jobId) {
                            const m = href.match(/jk=([a-f0-9]+)/i);
                            if (m) jobId = m[1];
                        }
                        jobUrl = href;
                    }

                    if (!jobId || seen.has(jobId)) return;
                    seen.add(jobId);

                    // Build proper job URL
                    if (!jobUrl || !jobUrl.includes('indeed')) {
                        jobUrl = window.location.origin + '/viewjob?jk=' + jobId;
                    }

                    // Extract title
                    const titleEl = card.querySelector(
                        '.jobTitle, [class*="jobTitle"], h2 a, .jcs-JobTitle, ' +
                        'a[id^="job_"] span, [class*="title"] a'
                    );
                    title = titleEl ? titleEl.textContent.trim() : '';

                    // Extract company (use specific selectors to avoid grabbing location too)
                    const compEl = card.querySelector(
                        '[data-testid="company-name"], .companyName, ' +
                        'span[class*="company"], .company_location .companyName'
                    );
                    if (compEl) {
                        // Get only the direct text, not child elements
                        company = compEl.childNodes.length > 0
                            ? Array.from(compEl.childNodes)
                                .filter(n => n.nodeType === 3)
                                .map(n => n.textContent.trim())
                                .join('') || compEl.textContent.trim()
                            : compEl.textContent.trim();
                    }

                    // Extract location (separate from company)
                    const locEl = card.querySelector(
                        '[data-testid="text-location"], .companyLocation, ' +
                        'div[class*="location"]:not([class*="company"])'
                    );
                    location = locEl ? locEl.textContent.trim() : '';

                    if (title) {
                        results.push({
                            external_id: 'indeed_' + jobId,
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

            // Fallback: look for mosaic job cards (newer Indeed layout)
            if (results.length === 0) {
                document.querySelectorAll('.mosaic-provider-jobcards a[data-jk]').forEach(a => {
                    const jk = a.getAttribute('data-jk');
                    if (jk && !seen.has(jk)) {
                        seen.add(jk);
                        const text = a.textContent.trim().split('\\n')[0].trim();
                        if (text && text.length > 3) {
                            results.push({
                                external_id: 'indeed_' + jk,
                                title: text.substring(0, 200),
                                company: null,
                                location: null,
                                job_url: window.location.origin + '/viewjob?jk=' + jk,
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

    async def _handle_popups(self, page):
        """Dismiss Indeed popups (cookie consent, notifications)."""
        try:
            for sel in [
                '#onetrust-accept-btn-handler',  # Cookie consent
                'button[aria-label="close"]',
                'button:has-text("No thanks")',
                'button:has-text("Skip")',
                '[class*="popover"] button[class*="close"]',
            ]:
                btn = page.locator(sel).first
                if await btn.count() > 0 and await btn.is_visible():
                    await btn.click()
                    await human_delay(0.5, 1)
                    break
        except Exception:
            pass

    def _requires_login(self) -> bool:
        """Indeed search works without login."""
        return False


async def main():
    import argparse

    parser = argparse.ArgumentParser(description="Indeed job scraper")
    parser.add_argument("--keywords", default="Engineering Manager")
    parser.add_argument("--location", default="Bengaluru")
    parser.add_argument("--limit", type=int, default=10, help="Number of NEW jobs to find")
    parser.add_argument("--dry-run", action="store_true", help="Don't write to DB")
    parser.add_argument("--debug", action="store_true", help="Enable debug screenshots")
    parser.add_argument("--india", action="store_true", default=True, help="Use in.indeed.com")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    scraper = IndeedScraper(dry_run=args.dry_run, debug=args.debug, india=args.india)
    jobs = await scraper.scrape(
        keywords=args.keywords,
        location=args.location,
        limit=args.limit,
    )

    print(f"\n=== Indeed Scrape Results ===")
    print(f"New jobs found: {len(jobs)}")
    for j in jobs:
        print(f"  - [{j['external_id']}] {j['title']} @ {j.get('company', 'N/A')}")
        print(f"    URL: {j['job_url']}")


if __name__ == "__main__":
    asyncio.run(main())
