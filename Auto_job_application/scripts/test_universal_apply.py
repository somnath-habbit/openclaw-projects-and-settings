#!/usr/bin/env python3
"""
Test script for Universal Apply Bot - apply to a single external job.

Handles the LinkedIn→External redirect flow:
  1. Login to LinkedIn (existing session)
  2. Navigate to job page
  3. Click "Apply" → redirect to company site
  4. Run UniversalApplyBot on the external site

Usage:
    python3 scripts/test_universal_apply.py --url "https://www.linkedin.com/jobs/view/4365467566/" --dry-run --debug
"""
import asyncio
import argparse
import logging
import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BASE_DIR))

from detached_flows.Playwright.browser_session import BrowserSession
from detached_flows.Playwright.universal_apply_bot import UniversalApplyBot, ApplyStatus
from detached_flows.LoginWrapper.login_manager import ensure_logged_in
from detached_flows.Playwright.page_utils import human_delay
from detached_flows.config import PROFILE_PATH, SCREENSHOTS_DIR


def setup_logging(debug: bool = False):
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s [%(name)-20s] %(levelname)-7s %(message)s',
        datefmt='%H:%M:%S'
    )
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('playwright').setLevel(logging.WARNING)


async def main():
    parser = argparse.ArgumentParser(description="Test Universal Apply Bot on a single job")
    parser.add_argument("--url", required=True, help="Job URL to apply to")
    parser.add_argument("--site", default="", help="Site name (auto-detected from URL if empty)")
    parser.add_argument("--dry-run", action="store_true", help="Fill forms but don't submit")
    parser.add_argument("--debug", action="store_true", help="Enable debug screenshots")
    parser.add_argument("--title", default="", help="Job title (for context)")
    parser.add_argument("--company", default="", help="Company name (for context)")
    args = parser.parse_args()

    setup_logging(args.debug)
    logger = logging.getLogger("TestUniversalApply")

    # Load profile
    try:
        with open(PROFILE_PATH) as f:
            profile = json.load(f)
        logger.info(f"Profile loaded: {profile.get('profile', {}).get('name', 'Unknown')}")
    except Exception as e:
        logger.error(f"Could not load profile from {PROFILE_PATH}: {e}")
        sys.exit(1)

    job_context = {}
    if args.title:
        job_context['title'] = args.title
    if args.company:
        job_context['company'] = args.company

    logger.info("=" * 60)
    logger.info("UNIVERSAL APPLY BOT - TEST RUN")
    logger.info("=" * 60)
    logger.info(f"Job URL:  {args.url}")
    logger.info(f"Site:     {args.site or '(auto-detect)'}")
    logger.info(f"Dry Run:  {args.dry_run}")
    logger.info(f"Debug:    {args.debug}")
    logger.info("=" * 60)

    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    session = BrowserSession()

    try:
        await session.launch()
        logger.info("Browser launched")
        page = session.page

        is_linkedin = 'linkedin.com' in args.url
        external_url = args.url

        # ===================================================
        # PHASE 1: If LinkedIn URL, login + get external URL
        # ===================================================
        if is_linkedin:
            logger.info("\n--- Phase 1: LinkedIn Login ---")
            logged_in = await ensure_logged_in(session)
            if not logged_in:
                logger.error("LinkedIn login failed")
                return 1
            logger.info("LinkedIn login OK")
            await session.save_session()

            logger.info(f"\n--- Phase 2: Navigate to job page ---")
            await page.goto(args.url, wait_until="domcontentloaded", timeout=30000)
            await human_delay(3, 5)

            ss = str(SCREENSHOTS_DIR / "test_universal_1_job_page.png")
            await page.screenshot(path=ss)
            logger.info(f"Screenshot: {ss}")

            # Find the Apply button (non-Easy Apply)
            logger.info("\n--- Phase 3: Find external Apply button ---")

            apply_info = await page.evaluate("""
                () => {
                    const results = { easy_apply: null, external: [] };

                    // Check Easy Apply
                    let eaBtn = document.querySelector('button[aria-label*="Easy Apply"]');
                    if (eaBtn) results.easy_apply = eaBtn.innerText.trim();

                    // Find all apply-related buttons/links
                    document.querySelectorAll('button, a').forEach(el => {
                        const text = (el.innerText || '').trim().toLowerCase();
                        if (text.includes('apply') && !text.includes('easy apply')) {
                            results.external.push({
                                tag: el.tagName,
                                text: el.innerText.trim(),
                                href: el.href || '',
                                ariaLabel: el.getAttribute('aria-label') || '',
                                classes: el.className.substring(0, 80),
                            });
                        }
                    });
                    return results;
                }
            """)

            logger.info(f"Easy Apply button: {apply_info.get('easy_apply', 'NOT FOUND')}")
            logger.info(f"External apply buttons: {len(apply_info.get('external', []))}")
            for btn in apply_info.get('external', []):
                logger.info(f"  [{btn['tag']}] '{btn['text']}' href={btn['href'][:80] if btn['href'] else 'none'}")

            if apply_info.get('easy_apply'):
                logger.warning("This job has Easy Apply, not an external application!")
                logger.info("The Universal Apply Bot is for external/company-site applications.")
                return 1

            if not apply_info.get('external'):
                logger.error("No apply button found at all on this page!")
                ss2 = str(SCREENSHOTS_DIR / "test_universal_2_no_apply.png")
                await page.screenshot(path=ss2)
                return 1

            # Click the external apply button
            logger.info("\n--- Phase 4: Click Apply → redirect to external site ---")

            # Listen for new tab/popup
            new_page_event = asyncio.Future()

            async def on_page(new_page):
                if not new_page_event.done():
                    new_page_event.set_result(new_page)

            session.context.on("page", on_page)

            clicked = await page.evaluate("""
                () => {
                    const buttons = document.querySelectorAll('button, a');
                    for (const btn of buttons) {
                        const text = (btn.innerText || '').trim().toLowerCase();
                        if (text.includes('apply') && !text.includes('easy apply')) {
                            btn.click();
                            return btn.innerText.trim();
                        }
                    }
                    return null;
                }
            """)
            logger.info(f"Clicked: '{clicked}'")

            # Wait for redirect or new tab
            await human_delay(3, 5)

            # Check if a new tab opened
            target_page = page
            try:
                new_page = await asyncio.wait_for(new_page_event, timeout=5.0)
                logger.info(f"New tab opened: {new_page.url[:100]}")
                await new_page.wait_for_load_state("domcontentloaded")
                target_page = new_page
                external_url = new_page.url
            except asyncio.TimeoutError:
                # No new tab — check if current page redirected
                if page.url != args.url:
                    logger.info(f"Redirected to: {page.url[:100]}")
                    external_url = page.url
                else:
                    logger.info("No redirect detected, checking for modal...")
                    # Maybe it opened a modal/dialog?
                    has_modal = await page.evaluate("""
                        () => {
                            const modals = document.querySelectorAll('[role="dialog"]:not([style*="display: none"]), .modal, [class*="modal"]');
                            return modals.length;
                        }
                    """)
                    if has_modal:
                        logger.info(f"Found {has_modal} modal(s) — might be an in-page application")
                    external_url = page.url

            ss3 = str(SCREENSHOTS_DIR / "test_universal_3_after_click.png")
            await target_page.screenshot(path=ss3)
            logger.info(f"Screenshot: {ss3}")
            logger.info(f"External URL: {external_url[:120]}")

            # Switch session page if new tab
            if target_page != page:
                session.page = target_page

        # ===================================================
        # PHASE 5: Run UniversalApplyBot on external site
        # ===================================================
        logger.info(f"\n--- Phase 5: Running UniversalApplyBot ---")
        logger.info(f"Target: {external_url[:120]}")

        bot = UniversalApplyBot(
            session=session,
            profile=profile,
            debug=args.debug,
            dry_run=args.dry_run,
        )

        result = await bot.apply_to_job(
            job_url=external_url,
            site_name=args.site,
            job_context=job_context,
        )

        # Print results
        logger.info("")
        logger.info("=" * 60)
        logger.info("RESULT")
        logger.info("=" * 60)
        logger.info(f"Status:          {result.status}")
        logger.info(f"Site:            {result.site_name}")
        logger.info(f"Pages navigated: {result.pages_navigated}")
        logger.info(f"Fields filled:   {result.fields_filled}")
        logger.info(f"Duration:        {result.duration_seconds:.1f}s")

        if result.errors:
            logger.info(f"Errors:")
            for err in result.errors:
                logger.info(f"  - {err}")

        if result.filled_fields_log:
            logger.info(f"Fields filled:")
            for fld in result.filled_fields_log:
                logger.info(f"  [{fld.get('type','')}] {fld.get('label','')}: {fld.get('value','')}")

        if result.screenshots:
            logger.info(f"Screenshots:")
            for ss in result.screenshots:
                logger.info(f"  {ss}")

        if result.status in (ApplyStatus.SUBMITTED, ApplyStatus.DRY_RUN, ApplyStatus.ALREADY_APPLIED):
            logger.info("\n✅ TEST PASSED")
            return 0
        else:
            logger.info("\n❌ TEST FAILED")
            return 1

    except Exception as e:
        logger.error(f"Test failed: {e}", exc_info=True)
        return 1

    finally:
        await session.close()
        logger.info("Browser closed")


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
