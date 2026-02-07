#!/usr/bin/env python3
"""
Scrape LinkedIn jobs WITHOUT the Easy Apply filter.
Identifies and saves both Easy Apply and External Apply jobs.

Usage:
    python scripts/scrape_linkedin_external.py --keywords "Engineering Manager" --location "Bengaluru" --limit 10 --dry-run
"""
import asyncio
import argparse
import logging
import sqlite3
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BASE_DIR.parent))

from detached_flows.Playwright.browser_session import BrowserSession
from detached_flows.LoginWrapper.login_manager import ensure_logged_in
from detached_flows.Playwright.page_utils import human_delay, nav_delay, page_load_delay
from detached_flows.config import DB_PATH, SCREENSHOTS_DIR

logger = logging.getLogger("LinkedInExternalScraper")


async def main():
    parser = argparse.ArgumentParser(description="Scrape LinkedIn for external apply jobs")
    parser.add_argument("--keywords", default="Engineering Manager")
    parser.add_argument("--location", default="Bengaluru")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    session = BrowserSession()
    db_path = str(DB_PATH)

    try:
        await session.launch()
        logger.info("Browser launched")

        # Login
        logged_in = await ensure_logged_in(session)
        if not logged_in:
            logger.error("Login failed")
            return
        await session.save_session()
        logger.info("Logged in to LinkedIn")

        page = session.page
        new_jobs = []
        external_jobs = []
        offset = 0
        max_pages = 3

        for page_num in range(max_pages):
            # Search WITHOUT f_AL=true (no Easy Apply filter)
            kw = args.keywords.replace(' ', '%20')
            loc = args.location.replace(' ', '%20')
            url = (
                f"https://www.linkedin.com/jobs/search/"
                f"?keywords={kw}&location={loc}&start={offset}"
            )

            logger.info(f"Searching page {page_num + 1}: offset={offset}")
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            await human_delay(5, 8)

            # Scroll to load all results
            await page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
            await human_delay(3, 5)
            await page.evaluate("() => window.scrollTo(0, 0)")
            await human_delay(2, 3)

            if args.debug:
                SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
                await page.screenshot(path=str(SCREENSHOTS_DIR / f"linkedin_ext_search_{offset}.png"))

            # Extract job IDs from search results
            raw_jobs = await page.evaluate("""() => {
                const seen = {};
                document.querySelectorAll('a[href*="/jobs/view/"]').forEach(a => {
                    const m = a.href.match(/\\/jobs\\/view\\/(\\d+)/);
                    if (m && !seen[m[1]]) {
                        let title = a.textContent.trim();
                        if (title.length > 150) title = title.split('\\n')[0].trim();
                        seen[m[1]] = title || null;
                    }
                });
                return seen;
            }""")

            logger.info(f"Found {len(raw_jobs)} jobs on page {page_num + 1}")

            # Visit each job to check if it's Easy Apply or External
            for jid, title in raw_jobs.items():
                if len(new_jobs) >= args.limit:
                    break

                # Check if already in DB
                conn = sqlite3.connect(db_path)
                exists = conn.execute(
                    "SELECT 1 FROM jobs WHERE external_id = ?", (jid,)
                ).fetchone()
                conn.close()
                if exists:
                    continue

                if title:
                    title = title.replace(" with verification", "").strip()
                    if "\n" in title:
                        title = title.split("\n")[0].strip()

                # Click on job to load details panel
                job_url = f"https://www.linkedin.com/jobs/view/{jid}/"
                try:
                    # Click the job card link
                    job_link = page.locator(f'a[href*="/jobs/view/{jid}"]').first
                    if await job_link.count() > 0:
                        await job_link.click()
                        await human_delay(2, 4)
                    else:
                        continue
                except Exception:
                    continue

                # Check for Easy Apply button vs Apply button
                apply_info = await page.evaluate("""() => {
                    // Check for Easy Apply button
                    const easyBtn = document.querySelector('button[aria-label*="Easy Apply"]');
                    if (easyBtn) return { type: 'easy_apply', url: '' };

                    // Check for external Apply button (links to external site)
                    const applyBtn = document.querySelector(
                        'button[aria-label*="Apply to"],' +
                        'a[href*="applyUrl"],' +
                        '.jobs-apply-button,' +
                        'button.jobs-apply-button'
                    );
                    if (applyBtn) {
                        const label = applyBtn.getAttribute('aria-label') || applyBtn.textContent || '';
                        if (label.includes('Easy Apply')) return { type: 'easy_apply', url: '' };
                        return { type: 'external', url: '' };
                    }

                    // Check for any apply-related link
                    const applyLink = document.querySelector('a[href*="redirect"]');
                    if (applyLink) return { type: 'external', url: applyLink.href };

                    return { type: 'unknown', url: '' };
                }""")

                # Extract company from details panel
                company = await page.evaluate("""() => {
                    const el = document.querySelector(
                        '.job-details-jobs-unified-top-card__company-name a,' +
                        '.jobs-unified-top-card__company-name a,' +
                        '.topcard__org-name-link,' +
                        '.job-details-jobs-unified-top-card__company-name'
                    );
                    return el ? el.textContent.trim() : null;
                }""")

                location_text = await page.evaluate("""() => {
                    const el = document.querySelector(
                        '.job-details-jobs-unified-top-card__primary-description-container .tvm__text,' +
                        '.jobs-unified-top-card__bullet,' +
                        '.topcard__flavor--bullet'
                    );
                    return el ? el.textContent.trim() : null;
                }""")

                apply_type = apply_info.get('type', 'unknown')

                job = {
                    'external_id': jid,
                    'title': title or 'Discovered Job',
                    'company': company,
                    'location': location_text or args.location,
                    'job_url': job_url,
                    'apply_type': 'Easy Apply' if apply_type == 'easy_apply' else 'Apply',
                    'site_apply_method': 'easy_apply' if apply_type == 'easy_apply' else 'redirect',
                }

                new_jobs.append(job)

                if apply_type != 'easy_apply':
                    external_jobs.append(job)
                    logger.info(f"  EXTERNAL: [{jid}] {title} @ {company}")
                else:
                    logger.info(f"  EASY:     [{jid}] {title} @ {company}")

                # Save to DB
                if not args.dry_run:
                    conn = sqlite3.connect(db_path)
                    conn.execute(
                        """INSERT OR IGNORE INTO jobs
                        (external_id, source, title, company, location, status, job_url,
                         apply_type, site_apply_method, enrich_status, discovered_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)""",
                        (
                            jid, "linkedin", job['title'], company,
                            job['location'], "NEW", job_url,
                            job['apply_type'], job['site_apply_method'],
                            "NEEDS_ENRICH",
                        ),
                    )
                    conn.commit()
                    conn.close()
                else:
                    logger.info(f"  [DRY RUN] Would save: {job['title']} ({apply_type})")

                await human_delay(1, 2)

            if len(new_jobs) >= args.limit:
                break
            offset += 25
            await nav_delay()

        await session.save_session()

        # Summary
        print(f"\n{'='*60}")
        print(f"LINKEDIN SCRAPE RESULTS")
        print(f"{'='*60}")
        print(f"Total new jobs:    {len(new_jobs)}")
        print(f"Easy Apply:        {len(new_jobs) - len(external_jobs)}")
        print(f"External Apply:    {len(external_jobs)}")
        print(f"{'='*60}")

        if external_jobs:
            print(f"\nExternal Apply Jobs (ready for UniversalApplyBot):")
            for j in external_jobs:
                print(f"  [{j['external_id']}] {j['title']} @ {j.get('company', 'N/A')}")
                print(f"    URL: {j['job_url']}")

    finally:
        await session.close()
        logger.info("Browser closed")


if __name__ == "__main__":
    asyncio.run(main())
