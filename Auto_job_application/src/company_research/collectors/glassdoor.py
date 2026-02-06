"""
Glassdoor Collector

Attempts to collect employee reviews and ratings from Glassdoor
Note: This is best-effort scraping and may fail due to anti-bot measures
"""

import asyncio
import time
from typing import Optional


class GlassdoorCollector:
    """Collect employee sentiment data from Glassdoor"""

    def __init__(self):
        self.name = "glassdoor"

    def collect(self, company_name: str, progress_callback=None) -> dict:
        """
        Collect Glassdoor data

        Args:
            company_name: Name of the company
            progress_callback: Optional callback for progress updates

        Returns:
            dict: Glassdoor data or error
        """
        try:
            if progress_callback:
                progress_callback(f"Collecting Glassdoor data for {company_name}...")

            # Run async scraping in sync context
            data = asyncio.run(self._scrape_glassdoor(company_name, progress_callback))

            if data:
                if progress_callback:
                    rating = data.get('overall_rating', 'N/A')
                    progress_callback(f"✓ Glassdoor data collected (Rating: {rating}/5.0)")

                return {'success': True, 'data': data}
            else:
                raise Exception("No data collected")

        except Exception as e:
            error_msg = f"Glassdoor collection failed: {str(e)}"
            if progress_callback:
                progress_callback(f"✗ {error_msg}")

            # Return partial data structure so scoring can handle it
            return {
                'success': False,
                'error': error_msg,
                'data': {
                    'overall_rating': None,
                    'ceo_approval': None,
                    'recommend_to_friend': None,
                    'review_count': 0,
                    'reviews': []
                }
            }

    async def _scrape_glassdoor(self, company_name: str, progress_callback=None) -> Optional[dict]:
        """
        Attempt to scrape Glassdoor using Playwright

        Args:
            company_name: Company name
            progress_callback: Progress callback

        Returns:
            dict: Collected data or None
        """
        try:
            from playwright.async_api import async_playwright

            async with async_playwright() as p:
                # Launch browser
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context(
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                )
                page = await context.new_page()

                # Search for company on Glassdoor
                search_url = f"https://www.glassdoor.com/Search/results.htm?keyword={company_name.replace(' ', '%20')}"

                if progress_callback:
                    progress_callback(f"Navigating to Glassdoor...")

                await page.goto(search_url, wait_until='domcontentloaded', timeout=15000)
                await asyncio.sleep(2)  # Human-like delay

                # Try to find company link
                try:
                    # Look for the first company result
                    company_link = await page.locator('a[data-test="employer-link"]').first.get_attribute('href', timeout=5000)

                    if not company_link:
                        raise Exception("Company not found on Glassdoor")

                    full_url = f"https://www.glassdoor.com{company_link}" if company_link.startswith('/') else company_link

                    if progress_callback:
                        progress_callback(f"Found company page, extracting data...")

                    await page.goto(full_url, wait_until='domcontentloaded', timeout=15000)
                    await asyncio.sleep(3)

                    # Extract data
                    data = await self._extract_data_from_page(page)

                    await browser.close()
                    return data

                except Exception as e:
                    await browser.close()
                    raise Exception(f"Failed to find company: {str(e)}")

        except Exception as e:
            # Return None on any error - caller will handle
            return None

    async def _extract_data_from_page(self, page) -> dict:
        """
        Extract ratings and data from Glassdoor company page

        Args:
            page: Playwright page object

        Returns:
            dict: Extracted data
        """
        data = {
            'overall_rating': None,
            'ceo_approval': None,
            'recommend_to_friend': None,
            'review_count': 0,
            'reviews': []
        }

        # Try to extract overall rating
        try:
            rating_elem = await page.locator('[data-test="rating"]').first.inner_text(timeout=3000)
            data['overall_rating'] = float(rating_elem)
        except:
            pass

        # Try to extract CEO approval
        try:
            ceo_elem = await page.locator('text=/CEO Approval/').locator('..').locator('text=/%/').inner_text(timeout=3000)
            data['ceo_approval'] = int(ceo_elem.replace('%', ''))
        except:
            pass

        # Try to extract recommend percentage
        try:
            recommend_elem = await page.locator('text=/Recommend to a friend/').locator('..').locator('text=/%/').inner_text(timeout=3000)
            data['recommend_to_friend'] = int(recommend_elem.replace('%', ''))
        except:
            pass

        # Try to get review count
        try:
            count_elem = await page.locator('text=/Reviews/').first.inner_text(timeout=3000)
            # Extract number from text like "1,234 Reviews"
            import re
            match = re.search(r'([\d,]+)', count_elem)
            if match:
                data['review_count'] = int(match.group(1).replace(',', ''))
        except:
            pass

        return data
