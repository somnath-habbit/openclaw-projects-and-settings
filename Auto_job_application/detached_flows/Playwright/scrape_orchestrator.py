"""
Multi-Site Scrape Orchestrator - Runs scrapers across multiple job sites.

Coordinates scraping from Naukri, Indeed, Instahyre (and LinkedIn)
with rate limiting, error handling, and aggregate reporting.

Usage:
    orchestrator = ScrapeOrchestrator(sites=["naukri", "indeed"], dry_run=True)
    results = await orchestrator.scrape_all(keywords="DevOps", location="Bengaluru", limit=10)

    # Or as CLI:
    python scrape_orchestrator.py --sites naukri indeed --keywords "DevOps" --limit 10
"""
import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Optional

from detached_flows.Playwright.browser_session import BrowserSession
from detached_flows.Playwright.page_utils import human_delay
from detached_flows.config import DELAY_BETWEEN_APPLICATIONS

logger = logging.getLogger("ScrapeOrchestrator")


# Scraper registry - maps site names to scraper classes
SCRAPER_REGISTRY = {}


def _load_scrapers():
    """Lazily load scraper classes to avoid circular imports."""
    global SCRAPER_REGISTRY
    if SCRAPER_REGISTRY:
        return

    from detached_flows.Playwright.naukri_scraper import NaukriScraper
    from detached_flows.Playwright.indeed_scraper import IndeedScraper
    from detached_flows.Playwright.instahyre_scraper import InstahyreScraper

    SCRAPER_REGISTRY = {
        "naukri": NaukriScraper,
        "indeed": IndeedScraper,
        "instahyre": InstahyreScraper,
    }


# Default sites to scrape (in order)
DEFAULT_SITES = ["naukri", "indeed"]


class ScrapeResult:
    """Result from scraping a single site."""

    def __init__(self, site_name: str):
        self.site_name = site_name
        self.new_jobs: List[dict] = []
        self.total_found: int = 0
        self.status: str = "PENDING"  # PENDING, SUCCESS, FAILED, SKIPPED
        self.error: str = ""
        self.duration_seconds: float = 0.0

    def __repr__(self):
        return (
            f"ScrapeResult({self.site_name}: {self.status}, "
            f"new={len(self.new_jobs)}, total={self.total_found})"
        )


class ScrapeOrchestrator:
    """
    Coordinates scraping across multiple job sites.

    Features:
    - Sequential site scraping (shared browser session)
    - Rate limiting between sites
    - Per-site error isolation
    - Aggregate reporting
    """

    def __init__(
        self,
        sites: List[str] = None,
        dry_run: bool = False,
        debug: bool = False,
        delay_between_sites: int = 10,
    ):
        self.sites = sites or list(DEFAULT_SITES)
        self.dry_run = dry_run
        self.debug = debug
        self.delay_between_sites = delay_between_sites

    async def scrape_all(
        self,
        keywords: str = "Engineering Manager",
        location: str = "Bengaluru",
        limit_per_site: int = 10,
    ) -> Dict[str, ScrapeResult]:
        """
        Scrape all configured sites sequentially.

        Uses a shared browser session for efficiency.

        Args:
            keywords: Job search keywords
            location: Location filter
            limit_per_site: Number of new jobs to find per site

        Returns:
            Dict mapping site name to ScrapeResult
        """
        _load_scrapers()

        results = {}
        session = BrowserSession()

        try:
            await session.launch()
            logger.info("Browser launched for multi-site scraping")

            for i, site_name in enumerate(self.sites):
                site_name = site_name.lower().strip()

                if site_name not in SCRAPER_REGISTRY:
                    logger.warning(f"Unknown site: {site_name} - skipping")
                    result = ScrapeResult(site_name)
                    result.status = "SKIPPED"
                    result.error = f"No scraper registered for '{site_name}'"
                    results[site_name] = result
                    continue

                logger.info(f"\n{'='*50}")
                logger.info(f"Scraping {site_name.upper()} ({i+1}/{len(self.sites)})")
                logger.info(f"{'='*50}")

                result = await self._scrape_site(
                    session, site_name, keywords, location, limit_per_site
                )
                results[site_name] = result

                # Delay between sites
                if i < len(self.sites) - 1 and self.delay_between_sites > 0:
                    logger.info(
                        f"Waiting {self.delay_between_sites}s before next site..."
                    )
                    await asyncio.sleep(self.delay_between_sites)

        except Exception as e:
            logger.error(f"Orchestrator error: {e}", exc_info=True)

        finally:
            await session.close()
            logger.info("Browser closed")

        # Print summary
        self._print_summary(results)
        return results

    async def _scrape_site(
        self,
        session: BrowserSession,
        site_name: str,
        keywords: str,
        location: str,
        limit: int,
    ) -> ScrapeResult:
        """Scrape a single site with error isolation."""
        result = ScrapeResult(site_name)
        start_time = datetime.now()

        try:
            scraper_class = SCRAPER_REGISTRY[site_name]
            scraper = scraper_class(
                session=session,
                dry_run=self.dry_run,
                debug=self.debug,
            )

            jobs = await scraper.scrape(
                keywords=keywords,
                location=location,
                limit=limit,
            )

            result.new_jobs = jobs
            result.total_found = len(jobs)
            result.status = "SUCCESS"

        except Exception as e:
            logger.error(f"Failed to scrape {site_name}: {e}", exc_info=True)
            result.status = "FAILED"
            result.error = str(e)

        result.duration_seconds = (datetime.now() - start_time).total_seconds()
        return result

    def _print_summary(self, results: Dict[str, ScrapeResult]):
        """Print a summary of all scrape results."""
        logger.info(f"\n{'='*60}")
        logger.info("MULTI-SITE SCRAPE SUMMARY")
        logger.info(f"{'='*60}")

        total_new = 0
        for site_name, result in results.items():
            status_icon = {
                "SUCCESS": "+",
                "FAILED": "x",
                "SKIPPED": "-",
                "PENDING": "?",
            }.get(result.status, "?")

            logger.info(
                f"  [{status_icon}] {site_name:15s} | "
                f"new={len(result.new_jobs):3d} | "
                f"{result.duration_seconds:.1f}s | "
                f"{result.status}"
            )
            if result.error:
                logger.info(f"      Error: {result.error[:80]}")

            total_new += len(result.new_jobs)

        logger.info(f"{'='*60}")
        logger.info(f"Total new jobs: {total_new}")
        logger.info(f"{'='*60}")

    @staticmethod
    def available_sites() -> List[str]:
        """List all available scraper site names."""
        _load_scrapers()
        return list(SCRAPER_REGISTRY.keys())


async def main():
    import argparse

    parser = argparse.ArgumentParser(description="Multi-site job scraper orchestrator")
    parser.add_argument(
        "--sites", nargs="+", default=DEFAULT_SITES,
        help=f"Sites to scrape (available: naukri, indeed, instahyre)"
    )
    parser.add_argument("--keywords", default="Engineering Manager")
    parser.add_argument("--location", default="Bengaluru")
    parser.add_argument("--limit", type=int, default=10,
                        help="Number of NEW jobs per site")
    parser.add_argument("--dry-run", action="store_true", help="Don't write to DB")
    parser.add_argument("--debug", action="store_true", help="Enable debug screenshots")
    parser.add_argument("--delay", type=int, default=10,
                        help="Delay between sites in seconds")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    orchestrator = ScrapeOrchestrator(
        sites=args.sites,
        dry_run=args.dry_run,
        debug=args.debug,
        delay_between_sites=args.delay,
    )

    results = await orchestrator.scrape_all(
        keywords=args.keywords,
        location=args.location,
        limit_per_site=args.limit,
    )

    # Print job details
    for site_name, result in results.items():
        if result.new_jobs:
            print(f"\n--- {site_name.upper()} Jobs ---")
            for j in result.new_jobs:
                print(f"  [{j['external_id']}] {j['title']} @ {j.get('company', 'N/A')}")


if __name__ == "__main__":
    asyncio.run(main())
