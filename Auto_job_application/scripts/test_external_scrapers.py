#!/usr/bin/env python3
"""
Test script for external job site scrapers.

Tests individual scrapers or the multi-site orchestrator in dry-run mode.

Usage:
    # Test single scraper:
    python scripts/test_external_scrapers.py --site naukri --dry-run

    # Test all scrapers:
    python scripts/test_external_scrapers.py --all --dry-run

    # Test with real DB writes (careful!):
    python scripts/test_external_scrapers.py --site naukri --limit 5

    # Test orchestrator:
    python scripts/test_external_scrapers.py --orchestrator --sites naukri indeed --dry-run
"""
import asyncio
import argparse
import logging
import sys
from pathlib import Path

# Setup paths
BASE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BASE_DIR.parent))


def setup_logging(debug: bool = False):
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s [%(name)-20s] %(levelname)-7s %(message)s',
        datefmt='%H:%M:%S'
    )
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('playwright').setLevel(logging.WARNING)


async def test_single_scraper(site: str, keywords: str, location: str,
                               limit: int, dry_run: bool, debug: bool):
    """Test a single scraper."""
    logger = logging.getLogger("TestScraper")

    # Import the right scraper
    scraper = None
    if site == "naukri":
        from detached_flows.Playwright.naukri_scraper import NaukriScraper
        scraper = NaukriScraper(dry_run=dry_run, debug=debug)
    elif site == "indeed":
        from detached_flows.Playwright.indeed_scraper import IndeedScraper
        scraper = IndeedScraper(dry_run=dry_run, debug=debug)
    elif site == "instahyre":
        from detached_flows.Playwright.instahyre_scraper import InstahyreScraper
        scraper = InstahyreScraper(dry_run=dry_run, debug=debug)
    else:
        logger.error(f"Unknown site: {site}")
        return 1

    logger.info("=" * 60)
    logger.info(f"TESTING {site.upper()} SCRAPER")
    logger.info("=" * 60)
    logger.info(f"Keywords: {keywords}")
    logger.info(f"Location: {location}")
    logger.info(f"Limit:    {limit}")
    logger.info(f"Dry Run:  {dry_run}")
    logger.info("=" * 60)

    try:
        jobs = await scraper.scrape(
            keywords=keywords,
            location=location,
            limit=limit,
        )

        logger.info("")
        logger.info("=" * 60)
        logger.info("RESULTS")
        logger.info("=" * 60)
        logger.info(f"New jobs found: {len(jobs)}")

        for j in jobs:
            logger.info(f"  [{j['external_id']}] {j['title']}")
            logger.info(f"    Company:  {j.get('company', 'N/A')}")
            logger.info(f"    Location: {j.get('location', 'N/A')}")
            logger.info(f"    URL:      {j.get('job_url', 'N/A')}")

        if jobs:
            logger.info("")
            logger.info("TEST PASSED")
            return 0
        else:
            logger.info("")
            logger.info("TEST COMPLETED (no new jobs found - may already be in DB)")
            return 0

    except Exception as e:
        logger.error(f"Test failed: {e}", exc_info=True)
        return 1


async def test_orchestrator(sites: list, keywords: str, location: str,
                            limit: int, dry_run: bool, debug: bool):
    """Test the multi-site orchestrator."""
    logger = logging.getLogger("TestOrchestrator")

    from detached_flows.Playwright.scrape_orchestrator import ScrapeOrchestrator

    logger.info("=" * 60)
    logger.info("TESTING MULTI-SITE ORCHESTRATOR")
    logger.info("=" * 60)
    logger.info(f"Sites:    {', '.join(sites)}")
    logger.info(f"Keywords: {keywords}")
    logger.info(f"Location: {location}")
    logger.info(f"Limit:    {limit} per site")
    logger.info(f"Dry Run:  {dry_run}")
    logger.info("=" * 60)

    orchestrator = ScrapeOrchestrator(
        sites=sites,
        dry_run=dry_run,
        debug=debug,
        delay_between_sites=5,
    )

    try:
        results = await orchestrator.scrape_all(
            keywords=keywords,
            location=location,
            limit_per_site=limit,
        )

        total_new = sum(len(r.new_jobs) for r in results.values())
        failed = sum(1 for r in results.values() if r.status == "FAILED")

        logger.info("")
        logger.info("=" * 60)
        logger.info("ORCHESTRATOR RESULTS")
        logger.info("=" * 60)
        logger.info(f"Total new jobs: {total_new}")
        logger.info(f"Failed sites:   {failed}")

        for site, result in results.items():
            logger.info(f"  {site}: {result.status} ({len(result.new_jobs)} new, {result.duration_seconds:.1f}s)")
            for j in result.new_jobs:
                logger.info(f"    - {j['title']} @ {j.get('company', 'N/A')}")

        if failed == 0:
            logger.info("")
            logger.info("TEST PASSED")
            return 0
        else:
            logger.info("")
            logger.info(f"TEST PARTIAL ({failed} site(s) failed)")
            return 1

    except Exception as e:
        logger.error(f"Orchestrator test failed: {e}", exc_info=True)
        return 1


async def test_all(keywords: str, location: str, limit: int,
                   dry_run: bool, debug: bool):
    """Test all scrapers individually."""
    logger = logging.getLogger("TestAll")

    sites = ["naukri", "indeed", "instahyre"]
    results = {}

    for site in sites:
        logger.info(f"\n{'#' * 60}")
        logger.info(f"Testing {site}...")
        logger.info(f"{'#' * 60}")

        exit_code = await test_single_scraper(
            site=site,
            keywords=keywords,
            location=location,
            limit=limit,
            dry_run=dry_run,
            debug=debug,
        )
        results[site] = exit_code

    logger.info(f"\n{'=' * 60}")
    logger.info("ALL SCRAPERS TESTED")
    logger.info(f"{'=' * 60}")
    for site, code in results.items():
        status = "PASSED" if code == 0 else "FAILED"
        logger.info(f"  {site}: {status}")

    return 1 if any(v != 0 for v in results.values()) else 0


async def main():
    parser = argparse.ArgumentParser(description="Test external job scrapers")
    parser.add_argument("--site", default="", help="Single site to test (naukri, indeed, instahyre)")
    parser.add_argument("--all", action="store_true", help="Test all scrapers")
    parser.add_argument("--orchestrator", action="store_true", help="Test orchestrator")
    parser.add_argument("--sites", nargs="+", default=["naukri", "indeed"],
                        help="Sites for orchestrator test")
    parser.add_argument("--keywords", default="Engineering Manager")
    parser.add_argument("--location", default="Bengaluru")
    parser.add_argument("--limit", type=int, default=5, help="Jobs per site")
    parser.add_argument("--dry-run", action="store_true", help="Don't write to DB")
    parser.add_argument("--debug", action="store_true", help="Enable debug screenshots")
    args = parser.parse_args()

    setup_logging(args.debug)

    if args.all:
        exit_code = await test_all(
            args.keywords, args.location, args.limit, args.dry_run, args.debug
        )
    elif args.orchestrator:
        exit_code = await test_orchestrator(
            args.sites, args.keywords, args.location, args.limit,
            args.dry_run, args.debug
        )
    elif args.site:
        exit_code = await test_single_scraper(
            args.site, args.keywords, args.location, args.limit,
            args.dry_run, args.debug
        )
    else:
        parser.print_help()
        print("\nExamples:")
        print("  python scripts/test_external_scrapers.py --site naukri --dry-run")
        print("  python scripts/test_external_scrapers.py --all --dry-run")
        print("  python scripts/test_external_scrapers.py --orchestrator --dry-run")
        exit_code = 0

    sys.exit(exit_code)


if __name__ == "__main__":
    asyncio.run(main())
