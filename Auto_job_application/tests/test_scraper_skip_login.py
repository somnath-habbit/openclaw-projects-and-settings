#!/usr/bin/env python3
"""
Test scraper with login check disabled (assumes active session).
Use this when credential broker isn't working but you have an active LinkedIn session.
"""
import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

# Load .env file
from dotenv import load_dotenv
env_path = Path(__file__).parent / ".env"
if env_path.exists():
    load_dotenv(env_path)
    print(f"✓ Loaded environment from {env_path}")

# Monkey-patch the login check to always return True
from detached_flows.LoginWrapper import login_manager

original_ensure_logged_in = login_manager.ensure_logged_in


async def mock_ensure_logged_in(session):
    """Mock login check - assumes session is valid."""
    print("⚠️  [MOCK] Skipping login check, assuming active session...")
    # Just navigate to LinkedIn to verify session works
    await session.page.goto("https://www.linkedin.com", wait_until="networkidle", timeout=30000)
    print("✓ Navigated to LinkedIn successfully")
    return True


# Apply the monkey patch
login_manager.ensure_logged_in = mock_ensure_logged_in

# Now import and run the scraper
from detached_flows.Playwright.linkedin_scraper import PlaywrightScraper
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s"
)


async def main():
    print("\n" + "="*60)
    print("Testing Playwright Scraper (Login Check DISABLED)")
    print("="*60 + "\n")

    print("⚠️  WARNING: This test assumes you have an active LinkedIn session.")
    print("   If the session is expired, scraping will fail.\n")

    scraper = PlaywrightScraper(dry_run=False, debug=True)

    jobs = await scraper.scrape(
        keywords="Engineering Manager",
        location="Bengaluru",
        limit=5,
    )

    print("\n" + "="*60)
    print("Test Results")
    print("="*60)
    print(f"New jobs found: {len(jobs)}")
    for j in jobs:
        print(f"  - [{j['external_id']}] {j['title']} @ {j.get('company', 'N/A')}")
    print("\nCheck data/screenshots/ for debug screenshots")
    print("="*60 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
