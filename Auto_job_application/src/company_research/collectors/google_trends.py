"""
Google Trends Collector

Collects search interest data from Google Trends
"""

import time
from typing import Optional


class GoogleTrendsCollector:
    """Collect Google Trends data for company brand awareness"""

    def __init__(self):
        self.name = "google_trends"

    def collect(self, company_name: str, progress_callback=None) -> dict:
        """
        Collect Google Trends data

        Args:
            company_name: Name of the company
            progress_callback: Optional callback for progress updates

        Returns:
            dict: Trends data or error
        """
        try:
            if progress_callback:
                progress_callback(f"Collecting Google Trends for {company_name}...")

            from pytrends.request import TrendReq

            pytrends = TrendReq(hl='en-US', tz=360, timeout=(10, 25))

            # Global trends (last 12 months)
            pytrends.build_payload([company_name], timeframe='today 12-m')
            time.sleep(1)  # Rate limiting

            global_trends = pytrends.interest_over_time()

            # India-specific trends
            pytrends.build_payload([company_name], timeframe='today 12-m', geo='IN')
            time.sleep(1)

            india_trends = pytrends.interest_over_time()

            # Regional breakdown (India)
            india_regions = pytrends.interest_by_region(resolution='REGION')

            # Calculate metrics
            global_avg = float(global_trends[company_name].mean()) if not global_trends.empty else 0
            india_avg = float(india_trends[company_name].mean()) if not india_trends.empty else 0

            # Trend direction (comparing recent vs older data)
            trend_direction = 'stable'
            if not india_trends.empty:
                recent = india_trends[company_name].tail(3).mean()
                older = india_trends[company_name].head(3).mean()

                if recent > older * 1.15:
                    trend_direction = 'rising'
                elif recent < older * 0.85:
                    trend_direction = 'falling'

            # Convert regions to dict
            india_regions_dict = {}
            if not india_regions.empty:
                india_regions_dict = india_regions[company_name].to_dict()

            data = {
                'global_interest_avg': round(global_avg, 2),
                'india_interest_avg': round(india_avg, 2),
                'trend_direction': trend_direction,
                'india_regions': india_regions_dict,
                'has_data': global_avg > 0 or india_avg > 0
            }

            if progress_callback:
                progress_callback(f"✓ Google Trends collected (India interest: {india_avg:.1f}/100)")

            return {'success': True, 'data': data}

        except Exception as e:
            error_msg = f"Google Trends collection failed: {str(e)}"
            if progress_callback:
                progress_callback(f"✗ {error_msg}")

            return {'success': False, 'error': error_msg, 'data': {}}
