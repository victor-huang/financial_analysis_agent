"""Financial data fetcher module for retrieving financial data from various sources."""

import logging
from typing import Dict, List, Optional, Union
from datetime import datetime

import pandas as pd

from ..config import get_config
from .sources import YFinanceSource, AlphaVantageSource, FinnhubSource, YahooQuerySource
from .utils import merge_estimates_on_period_end

logger = logging.getLogger(__name__)


class FinancialDataFetcher:
    """Class to fetch financial data from various sources."""

    def __init__(self, api_key: str = None):
        """Initialize the financial data fetcher.

        Args:
            api_key: Alpha Vantage API key. If not provided, will try to get from config.
        """
        self.config = get_config()

        # Alpha Vantage setup
        self.alpha_vantage_key = api_key or self.config.get(
            "apis.alpha_vantage.api_key"
        )
        self._alpha_vantage_source = None

        # Finnhub setup
        self.finnhub_key = self.config.get("apis.finnhub.api_key") or self.config.get(
            "FINNHUB_API_KEY"
        )
        self._finnhub_source = None

        # YFinance and YahooQuery sources (no API key needed)
        self._yfinance_source = YFinanceSource()
        self._yahooquery_source = YahooQuerySource()

    @property
    def alpha_vantage_source(self) -> Optional[AlphaVantageSource]:
        """Get or initialize the Alpha Vantage source."""
        if not self._alpha_vantage_source and self.alpha_vantage_key:
            self._alpha_vantage_source = AlphaVantageSource(self.alpha_vantage_key)
        return self._alpha_vantage_source

    @property
    def finnhub_source(self) -> Optional[FinnhubSource]:
        """Get or initialize the Finnhub source."""
        if not self._finnhub_source and self.finnhub_key:
            self._finnhub_source = FinnhubSource(self.finnhub_key)
        return self._finnhub_source

    def get_stock_data(
        self,
        ticker: str,
        start_date: Union[str, datetime] = None,
        end_date: Union[str, datetime] = None,
        interval: str = "1d",
        source: str = "yfinance",
        period: Optional[str] = None,
    ) -> pd.DataFrame:
        """Get historical stock data for a given ticker.

        Args:
            ticker: Stock ticker symbol
            start_date: Start date for data (default: 1 year ago)
            end_date: End date for data (default: today)
            interval: Data interval ('1d', '1wk', '1mo')
            source: Data source ('yfinance' or 'alpha_vantage')
            period: Alternative to start/end date, e.g., '1y', '6mo'

        Returns:
            DataFrame with historical stock data
        """
        try:
            if source.lower() == "yfinance":
                return self._yfinance_source.get_stock_data(
                    ticker, start_date, end_date, interval, period
                )
            elif source.lower() == "alpha_vantage":
                if not self.alpha_vantage_source:
                    raise ValueError("Alpha Vantage API key not configured")
                return self.alpha_vantage_source.get_stock_data(ticker, interval)
            else:
                raise ValueError(f"Unsupported data source: {source}")
        except Exception as e:
            logger.error(f"Error fetching stock data for {ticker}: {str(e)}")
            raise

    def get_company_info(self, ticker: str) -> Dict:
        """Get company information."""
        return self._yfinance_source.get_company_info(ticker)

    def get_company_news(self, ticker: str, limit: int = 10) -> List[Dict]:
        """Get recent news articles about the company."""
        return self._yfinance_source.get_company_news(ticker, limit)

    def get_financials(
        self,
        ticker: str,
        statement_type: str = "income",
        period: str = "annual",
        limit: int = 4,
    ) -> Optional[pd.DataFrame]:
        """Get financial statements."""
        return self._yfinance_source.get_financials(
            ticker, statement_type, period, limit
        )

    def get_earnings_dates(self, ticker: str, limit: int = 8) -> Optional[pd.DataFrame]:
        """Get recent earnings dates with EPS estimates/actuals/surprise."""
        return self._yfinance_source.get_earnings_dates(ticker, limit)

    def get_earnings_trend(self, ticker: str) -> Optional[pd.DataFrame]:
        """Get earnings trend which may include quarterly EPS and revenue estimates."""
        return self._yfinance_source.get_earnings_trend(ticker)

    def get_analyst_estimates_yq(self, ticker: str) -> Optional[pd.DataFrame]:
        """Fetch analyst EPS and revenue estimates per quarter using yahooquery."""
        return self._yahooquery_source.get_analyst_estimates(ticker)

    def get_analyst_estimates_finnhub(
        self, ticker: str, limit: int = 8
    ) -> Optional[pd.DataFrame]:
        """Fetch quarterly analyst estimates (EPS and revenue) from Finnhub."""
        if not self.finnhub_source:
            return None
        return self.finnhub_source.get_analyst_estimates(ticker, limit)

    def get_revenue_estimates_finnhub(self, ticker: str) -> Optional[pd.DataFrame]:
        """Call Finnhub company-revenue-estimates API and normalize."""
        if not self.finnhub_source:
            return None
        return self.finnhub_source.get_revenue_estimates(ticker)

    def get_analyst_estimates(self, ticker: str) -> Optional[pd.DataFrame]:
        """Unified analyst estimates: prefer Finnhub, then YahooQuery, then yfinance history.

        Returns normalized DataFrame with ['period','endDate','epsEstimateAvg','revenueEstimateAvg'] when possible.
        """
        # Step 1: Try Finnhub (EPS+revenue via company_estimates/fallback)
        fh = self.get_analyst_estimates_finnhub(ticker)
        if fh is not None and not fh.empty:
            # If revenue missing, try to enrich with Finnhub revenue estimates endpoint
            if (
                "revenueEstimateAvg" not in fh.columns
                or fh["revenueEstimateAvg"].isna().all()
            ):
                rev = self.get_revenue_estimates_finnhub(ticker)
                if rev is not None and not rev.empty:
                    fh = merge_estimates_on_period_end(fh, rev)
            logger.info(
                "Analyst estimates source selected for %s: %s%s",
                ticker,
                "get_analyst_estimates_finnhub",
                (
                    " + revenue_enriched"
                    if (
                        "revenueEstimateAvg" in fh.columns
                        and fh["revenueEstimateAvg"].notna().any()
                    )
                    else ""
                ),
            )
            return fh

        # Step 2: YahooQuery
        yq = self.get_analyst_estimates_yq(ticker)
        if yq is not None and not yq.empty:
            logger.info(
                "Analyst estimates source selected for %s: %s",
                ticker,
                "get_analyst_estimates_yq",
            )
            return yq

        # Step 3: yfinance history (likely EPS only)
        yf_hist = self.get_earnings_trend(ticker)
        if yf_hist is not None and not yf_hist.empty:
            logger.info(
                "Analyst estimates source selected for %s: %s",
                ticker,
                "get_earnings_trend",
            )
            return yf_hist
        return None
