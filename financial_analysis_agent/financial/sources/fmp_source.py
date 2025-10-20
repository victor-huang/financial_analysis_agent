"""Financial Modeling Prep (FMP) data source module for retrieving financial data."""

import logging
from typing import Optional
import pandas as pd
import requests

from ..utils.date_utils import parse_quarter_end

logger = logging.getLogger(__name__)


class FMPSource:
    """Class to fetch financial data from Financial Modeling Prep API."""

    BASE_URL = "https://financialmodelingprep.com/api/v3"

    def __init__(self, api_key: str):
        """Initialize the FMP data source.

        Args:
            api_key: Financial Modeling Prep API key
        """
        self.api_key = api_key

    def _make_request(self, endpoint: str, params: dict = None) -> Optional[dict]:
        """Make a request to the FMP API.

        Args:
            endpoint: API endpoint path
            params: Additional query parameters

        Returns:
            JSON response as dict or None on error
        """
        if params is None:
            params = {}
        params['apikey'] = self.api_key

        url = f"{self.BASE_URL}/{endpoint}"

        try:
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"FMP API request failed for {endpoint}: {e}")
            return None

    def get_analyst_estimates(self, ticker: str, limit: int = 24) -> Optional[pd.DataFrame]:
        """Fetch quarterly analyst estimates (EPS and revenue) from FMP.

        Args:
            ticker: Stock ticker symbol
            limit: Maximum number of quarters to return

        Returns:
            DataFrame with columns: ['period', 'endDate', 'epsEstimateAvg',
                                     'epsActual', 'revenueEstimateAvg', 'revenueActual']
        """
        try:
            logger.info(f"Fetching quarterly analyst estimates from FMP for {ticker}")

            # FMP has a combined analyst-estimates endpoint
            # IMPORTANT: Use period=quarter to get quarterly estimates instead of annual fiscal year estimates
            data = self._make_request(f"analyst-estimates/{ticker}", params={'limit': limit, 'period': 'quarter'})

            if not data or not isinstance(data, list):
                logger.warning(f"No analyst estimates data from FMP for {ticker}")
                return None

            df = pd.DataFrame(data)

            if df.empty:
                return None

            logger.info(f"FMP analyst estimates columns for {ticker}: {list(df.columns)}")
            logger.info(f"FMP analyst estimates sample rows for {ticker}: {df.head(3).to_dict(orient='records')}")

            # Normalize to standard format
            out = pd.DataFrame()

            # Date fields - FMP uses 'date' for the quarter end date
            if 'date' in df.columns:
                out['endDate'] = pd.to_datetime(df['date'], errors='coerce')
                # Generate period label from date
                out['period'] = out['endDate'].apply(
                    lambda d: f"{d.year}Q{((d.month - 1)//3)+1}" if pd.notna(d) and hasattr(d, 'year') else None
                )

            # EPS estimates
            if 'estimatedEpsAvg' in df.columns:
                out['epsEstimateAvg'] = pd.to_numeric(df['estimatedEpsAvg'], errors='coerce')

            # EPS actual
            if 'estimatedEpsActual' in df.columns:
                out['epsActual'] = pd.to_numeric(df['estimatedEpsActual'], errors='coerce')

            # Revenue estimates - FMP provides in dollars
            if 'estimatedRevenueAvg' in df.columns:
                out['revenueEstimateAvg'] = pd.to_numeric(df['estimatedRevenueAvg'], errors='coerce')

            # Revenue actual
            if 'estimatedRevenueActual' in df.columns:
                out['revenueActual'] = pd.to_numeric(df['estimatedRevenueActual'], errors='coerce')

            # Sort by date descending (most recent first)
            if 'endDate' in out.columns:
                out = out.dropna(subset=['endDate']).sort_values('endDate', ascending=False)

            # Keep only relevant columns
            keep = [c for c in ['period', 'endDate', 'epsEstimateAvg', 'epsActual',
                                'revenueEstimateAvg', 'revenueActual'] if c in out.columns]

            if not keep:
                return None

            result = out[keep].head(limit)
            logger.info(f"FMP analyst estimates returned {len(result)} rows for {ticker}")
            return result

        except Exception as e:
            logger.error(f"Error fetching analyst estimates from FMP for {ticker}: {e}")
            return None

    def get_earnings_surprise(self, ticker: str, limit: int = 8) -> Optional[pd.DataFrame]:
        """Fetch earnings surprise data (historical EPS beat/miss) from FMP.

        Args:
            ticker: Stock ticker symbol
            limit: Maximum number of quarters to return

        Returns:
            DataFrame with EPS estimates vs actuals
        """
        try:
            logger.info(f"Fetching earnings surprise from FMP for {ticker}")

            data = self._make_request(f"earnings-surprises/{ticker}", params={'limit': limit})

            if not data or not isinstance(data, list):
                logger.warning(f"No earnings surprise data from FMP for {ticker}")
                return None

            df = pd.DataFrame(data)

            if df.empty:
                return None

            # Normalize
            out = pd.DataFrame()

            if 'date' in df.columns:
                out['endDate'] = pd.to_datetime(df['date'], errors='coerce')
                out['period'] = out['endDate'].apply(
                    lambda d: f"{d.year}Q{((d.month - 1)//3)+1}" if pd.notna(d) and hasattr(d, 'year') else None
                )

            if 'estimatedEarning' in df.columns:
                out['epsEstimateAvg'] = pd.to_numeric(df['estimatedEarning'], errors='coerce')

            if 'actualEarningResult' in df.columns:
                out['epsActual'] = pd.to_numeric(df['actualEarningResult'], errors='coerce')

            if 'endDate' in out.columns:
                out = out.dropna(subset=['endDate']).sort_values('endDate', ascending=False)

            keep = [c for c in ['period', 'endDate', 'epsEstimateAvg', 'epsActual'] if c in out.columns]

            if not keep:
                return None

            result = out[keep].head(limit)
            logger.info(f"FMP earnings surprise returned {len(result)} rows for {ticker}")
            return result

        except Exception as e:
            logger.error(f"Error fetching earnings surprise from FMP for {ticker}: {e}")
            return None

    def get_revenue_estimates(self, ticker: str, limit: int = 8) -> Optional[pd.DataFrame]:
        """Fetch revenue estimates from FMP.

        This is a convenience method that extracts revenue data from analyst estimates.

        Args:
            ticker: Stock ticker symbol
            limit: Maximum number of quarters to return

        Returns:
            DataFrame with ['period', 'endDate', 'revenueEstimateAvg', 'revenueActual']
        """
        estimates = self.get_analyst_estimates(ticker, limit)

        if estimates is None or estimates.empty:
            return None

        # Extract only revenue columns
        revenue_cols = [c for c in ['period', 'endDate', 'revenueEstimateAvg', 'revenueActual']
                        if c in estimates.columns]

        if not revenue_cols:
            return None

        return estimates[revenue_cols]

    def get_historical_earnings_calendar(self, ticker: str, limit: int = 20) -> Optional[pd.DataFrame]:
        """Fetch historical earnings calendar data from FMP.

        This endpoint provides both EPS and revenue actuals along with estimates.

        Args:
            ticker: Stock ticker symbol
            limit: Maximum number of earnings reports to return

        Returns:
            DataFrame with columns: ['announceDate', 'fiscalDateEnding', 'period',
                                     'epsEstimate', 'epsActual', 'revenueEstimate', 'revenueActual']
        """
        try:
            logger.info(f"Fetching historical earnings calendar from FMP for {ticker}")

            data = self._make_request(f"historical/earning_calendar/{ticker}", params={'limit': limit})

            if not data or not isinstance(data, list):
                logger.warning(f"No historical earnings calendar data from FMP for {ticker}")
                return None

            df = pd.DataFrame(data)

            if df.empty:
                return None

            logger.info(f"FMP historical earnings calendar columns for {ticker}: {list(df.columns)}")

            # Normalize to standard format
            out = pd.DataFrame()

            # Announcement date
            if 'date' in df.columns:
                out['announceDate'] = pd.to_datetime(df['date'], errors='coerce')

            # Fiscal period end date
            if 'fiscalDateEnding' in df.columns:
                out['fiscalDateEnding'] = pd.to_datetime(df['fiscalDateEnding'], errors='coerce')
                # Generate period label from fiscal date ending
                out['period'] = out['fiscalDateEnding'].apply(
                    lambda d: f"{d.year}Q{((d.month - 1)//3)+1}" if pd.notna(d) and hasattr(d, 'year') else None
                )

            # EPS estimates and actuals
            if 'epsEstimated' in df.columns:
                out['epsEstimate'] = pd.to_numeric(df['epsEstimated'], errors='coerce')
            if 'eps' in df.columns:
                out['epsActual'] = pd.to_numeric(df['eps'], errors='coerce')

            # Revenue estimates and actuals
            if 'revenueEstimated' in df.columns:
                out['revenueEstimate'] = pd.to_numeric(df['revenueEstimated'], errors='coerce')
            if 'revenue' in df.columns:
                out['revenueActual'] = pd.to_numeric(df['revenue'], errors='coerce')

            # Sort by announcement date descending (most recent first)
            if 'announceDate' in out.columns:
                out = out.dropna(subset=['announceDate']).sort_values('announceDate', ascending=False)

            # Keep only relevant columns
            keep = [c for c in ['announceDate', 'fiscalDateEnding', 'period', 'epsEstimate', 'epsActual',
                                'revenueEstimate', 'revenueActual'] if c in out.columns]

            if not keep:
                return None

            result = out[keep].head(limit)
            logger.info(f"FMP historical earnings calendar returned {len(result)} rows for {ticker}")
            return result

        except Exception as e:
            logger.error(f"Error fetching historical earnings calendar from FMP for {ticker}: {e}")
            return None
