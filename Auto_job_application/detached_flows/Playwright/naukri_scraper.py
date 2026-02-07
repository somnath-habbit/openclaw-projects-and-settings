"""
Naukri.com Scraper - Extracts job listings from Naukri.com search results.

Naukri is India's largest job portal. Jobs are rendered as cards with
structured data in the DOM. Supports keyword + location search with pagination.

Usage:
    scraper = NaukriScraper(dry_run=True, debug=True)
    jobs = await scraper.scrape(keywords="DevOps Engineer", location="Bengaluru", limit=10)

    # Or as CLI:
    python naukri_scraper.py --keywords "DevOps" --location "Bengaluru" --limit 5 --dry-run
"""
import asyncio
import logging
import re
from urllib.parse import quote_plus

from detached_flows.Playwright.base_scraper import BaseExternalScraper
from detached_flows.Playwright.page_utils import human_delay

logger = logging.getLogger("NaukriScraper")


class NaukriScraper(BaseExternalScraper):
    """Scraper for Naukri.com job listings."""

    SITE_NAME = "naukri"
    MAX_PAGES = 5
    RESULTS_PER_PAGE = 20

    def _build_search_url(self, keywords: str, location: str, offset: int) -> str:
        """Build Naukri search URL with keyword, location, and page offset."""
        # Naukri uses hyphenated keywords in URL path
        kw_slug = keywords.lower().replace(" ", "-")
        loc_slug = location.lower().replace(" ", "-")

        # Page number (1-indexed)
        page_num = (offset // self.RESULTS_PER_PAGE) + 1

        # Naukri search URL format
        url = f"https://www.naukri.com/{kw_slug}-jobs-in-{loc_slug}"
        if page_num > 1:
            url += f"-{page_num}"

        return url

    async def _extract_jobs_from_page(self, page) -> list[dict]:
        """Extract job listings from Naukri search results page."""
        jobs = await page.evaluate("""() => {
            const results = [];
            const seen = new Set();

            // Naukri job cards are typically in article elements or divs with job data
            const cards = document.querySelectorAll(
                'article.jobTuple, .jobTupleHeader, .srp-jobtuple-wrapper, ' +
                '[data-job-id], .cust-job-tuple, .list, ' +
                'a[href*="/job-listings-"], a[href*="/job/"]'
            );

            cards.forEach(card => {
                try {
                    let jobId = '';
                    let title = '';
                    let company = '';
                    let location = '';
                    let jobUrl = '';
                    let applyUrl = '';

                    // Try data-job-id attribute first
                    jobId = card.getAttribute('data-job-id') || '';

                    // Extract from link href
                    const link = card.tagName === 'A' ? card :
                                 card.querySelector('a[href*="/job-listings-"], a[href*="/job/"]');
                    if (link) {
                        jobUrl = link.href || '';
                        // Extract ID from URL: .../job-listings-xxx-123456 or .../job/title/id
                        if (!jobId) {
                            const m = jobUrl.match(/[/-](\\d{6,})/);
                            if (m) jobId = m[1];
                        }
                    }

                    if (!jobId || seen.has(jobId)) return;
                    seen.add(jobId);

                    // Extract title
                    const titleEl = card.querySelector(
                        '.title, .jobTitle, a.title, [class*="jobTitle"], ' +
                        '[class*="designation"], .row1 a, .info-heading'
                    );
                    title = titleEl ? titleEl.textContent.trim() : '';

                    // If card is a link, title might be the link text
                    if (!title && card.tagName === 'A') {
                        title = card.textContent.trim().split('\\n')[0].trim();
                    }

                    // Extract company
                    const compEl = card.querySelector(
                        '.subTitle, .companyName, [class*="companyInfo"], ' +
                        '[class*="company"], .info-company, .comp-name'
                    );
                    company = compEl ? compEl.textContent.trim() : '';

                    // Extract location
                    const locEl = card.querySelector(
                        '.locWdth, .location, [class*="location"], ' +
                        '[class*="placeholders"] li:first-child, .info-loc'
                    );
                    location = locEl ? locEl.textContent.trim() : '';

                    // Naukri apply URL (same as job URL typically)
                    applyUrl = jobUrl;

                    if (jobId && title) {
                        results.push({
                            external_id: 'naukri_' + jobId,
                            title: title.substring(0, 200),
                            company: company.substring(0, 200) || null,
                            location: location.substring(0, 200) || null,
                            job_url: jobUrl,
                            apply_url: applyUrl,
                            site_apply_method: 'external_form',
                        });
                    }
                } catch (e) {
                    // Skip malformed card
                }
            });

            // Fallback: extract from any links with job-related URLs
            if (results.length === 0) {
                document.querySelectorAll('a[href*="naukri.com"]').forEach(a => {
                    const href = a.href || '';
                    const m = href.match(/job-listings?-.*?(\\d{6,})/);
                    if (m && !seen.has(m[1])) {
                        seen.add(m[1]);
                        const text = a.textContent.trim().split('\\n')[0].trim();
                        if (text && text.length > 3 && text.length < 200) {
                            results.push({
                                external_id: 'naukri_' + m[1],
                                title: text,
                                company: null,
                                location: null,
                                job_url: href,
                                apply_url: href,
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
        """Dismiss Naukri login/notification popups."""
        try:
            # Close "Register now" or "Login" popups
            for sel in [
                'button[class*="close"]',
                '[class*="crossIcon"]',
                '[id*="close"]',
                'button:has-text("Not now")',
                'button:has-text("Maybe Later")',
            ]:
                btn = page.locator(sel).first
                if await btn.count() > 0 and await btn.is_visible():
                    await btn.click()
                    await human_delay(0.5, 1)
                    break
        except Exception:
            pass

    def _requires_login(self) -> bool:
        """Naukri search works without login, but login gets better results."""
        return False


async def main():
    import argparse

    parser = argparse.ArgumentParser(description="Naukri.com job scraper")
    parser.add_argument("--keywords", default="Engineering Manager")
    parser.add_argument("--location", default="Bengaluru")
    parser.add_argument("--limit", type=int, default=10, help="Number of NEW jobs to find")
    parser.add_argument("--dry-run", action="store_true", help="Don't write to DB")
    parser.add_argument("--debug", action="store_true", help="Enable debug screenshots")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    scraper = NaukriScraper(dry_run=args.dry_run, debug=args.debug)
    jobs = await scraper.scrape(
        keywords=args.keywords,
        location=args.location,
        limit=args.limit,
    )

    print(f"\n=== Naukri Scrape Results ===")
    print(f"New jobs found: {len(jobs)}")
    for j in jobs:
        print(f"  - [{j['external_id']}] {j['title']} @ {j.get('company', 'N/A')}")
        print(f"    URL: {j['job_url']}")


if __name__ == "__main__":
    asyncio.run(main())
