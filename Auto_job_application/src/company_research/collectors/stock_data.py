"""
Stock Market Data Collector

Collects stock data for public companies using Yahoo Finance
"""

from typing import Optional


class StockDataCollector:
    """Collect stock market data for public companies"""

    def __init__(self):
        self.name = "stock_market"

    def collect(self, company_name: str, progress_callback=None) -> dict:
        """
        Collect stock market data

        Args:
            company_name: Name of the company
            progress_callback: Optional callback for progress updates

        Returns:
            dict: Stock data or private company status
        """
        try:
            if progress_callback:
                progress_callback(f"Checking stock data for {company_name}...")

            import yfinance as yf

            # Try to find ticker symbol
            ticker_symbol = self._find_ticker(company_name)

            if not ticker_symbol:
                if progress_callback:
                    progress_callback(f"✓ {company_name} is a private company (no stock data)")

                return {
                    'success': True,
                    'data': {'status': 'private_company', 'ticker': None}
                }

            # Fetch stock data
            ticker = yf.Ticker(ticker_symbol)
            info = ticker.info
            history = ticker.history(period='1y')

            # Check if we got valid data
            if not info.get('currentPrice') and history.empty:
                return {
                    'success': True,
                    'data': {'status': 'private_company', 'ticker': None}
                }

            # Calculate performance
            perf_1mo = self._calc_performance(history, days=30)
            perf_3mo = self._calc_performance(history, days=90)
            perf_1yr = self._calc_performance(history, days=365)

            data = {
                'status': 'public_company',
                'ticker': ticker_symbol,
                'current_price': info.get('currentPrice'),
                'market_cap': info.get('marketCap'),
                'pe_ratio': info.get('trailingPE'),
                'performance_1mo': perf_1mo,
                'performance_3mo': perf_3mo,
                'performance_1yr': perf_1yr,
                'analyst_rating': info.get('recommendationKey'),
                '52_week_high': info.get('fiftyTwoWeekHigh'),
                '52_week_low': info.get('fiftyTwoWeekLow'),
                'profitable': info.get('profitMargins', 0) > 0
            }

            if progress_callback:
                progress_callback(f"✓ Stock data collected ({ticker_symbol})")

            return {'success': True, 'data': data}

        except Exception as e:
            error_msg = f"Stock data collection failed: {str(e)}"
            if progress_callback:
                progress_callback(f"✗ {error_msg}")

            return {'success': False, 'error': error_msg, 'data': {}}

    def _find_ticker(self, company_name: str) -> Optional[str]:
        """
        Attempt to find ticker symbol from company name

        Args:
            company_name: Company name

        Returns:
            Ticker symbol or None
        """
        import yfinance as yf

        # Try common variations
        variations = [
            company_name.upper(),
            company_name.split()[0].upper(),  # First word only
            company_name.replace(' ', '').upper()
        ]

        for ticker_guess in variations:
            try:
                ticker = yf.Ticker(ticker_guess)
                info = ticker.info

                # Check if we got valid data
                if info.get('longName') or info.get('shortName'):
                    # Verify it's the right company (basic check)
                    long_name = info.get('longName', '').lower()
                    if company_name.lower() in long_name or long_name in company_name.lower():
                        return ticker_guess
            except:
                continue

        return None

    def _calc_performance(self, history, days: int) -> Optional[float]:
        """
        Calculate stock performance over period

        Args:
            history: Price history DataFrame
            days: Number of days to look back

        Returns:
            Percentage change or None
        """
        try:
            if history.empty or len(history) < days:
                return None

            old_price = history['Close'].iloc[-days]
            current_price = history['Close'].iloc[-1]

            return round(((current_price - old_price) / old_price) * 100, 2)
        except:
            return None
