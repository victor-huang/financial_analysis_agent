"""Financial data fetcher module for retrieving financial data from various sources."""

import logging
from typing import Dict, List, Optional, Union
from datetime import datetime

import pandas as pd

from ..config import get_config
from .sources import YFinanceSource, AlphaVantageSource, FinnhubSource, YahooQuerySource, FMPSource
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

        # FMP setup
        self.fmp_key = self.config.get("apis.fmp.api_key") or self.config.get(
            "FMP_API_KEY"
        )
        self._fmp_source = None

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

    @property
    def fmp_source(self) -> Optional[FMPSource]:
        """Get or initialize the FMP source."""
        if not self._fmp_source and self.fmp_key:
            self._fmp_source = FMPSource(self.fmp_key)
        return self._fmp_source

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

    def get_analyst_estimates_fmp(
        self, ticker: str, limit: int = 8
    ) -> Optional[pd.DataFrame]:
        """Fetch quarterly analyst estimates (EPS and revenue) from FMP."""
        if not self.fmp_source:
            return None
        return self.fmp_source.get_analyst_estimates(ticker, limit)

    def get_revenue_estimates_fmp(self, ticker: str, limit: int = 8) -> Optional[pd.DataFrame]:
        """Call FMP analyst estimates API and extract revenue data."""
        if not self.fmp_source:
            return None
        return self.fmp_source.get_revenue_estimates(ticker, limit)

    def get_analyst_estimates(self, ticker: str) -> Optional[pd.DataFrame]:
        """Unified analyst estimates: prefer FMP, then Finnhub, then YahooQuery, then yfinance history.

        Returns normalized DataFrame with ['period','endDate','epsEstimateAvg','revenueEstimateAvg'] when possible.
        """
        logger.info("Starting analyst estimates search for %s with priority: FMP → Finnhub → YahooQuery → yfinance", ticker)

        # Step 1: Try FMP (has both EPS and revenue estimates, but often only annual/Q3 data)
        if not self.fmp_key:
            logger.info("FMP: Skipped (no API key configured)")
        else:
            logger.info("FMP: Trying...")
            fmp = self.get_analyst_estimates_fmp(ticker)
            if fmp is not None and not fmp.empty:
                has_eps = "epsEstimateAvg" in fmp.columns and fmp["epsEstimateAvg"].notna().any()
                has_revenue = "revenueEstimateAvg" in fmp.columns and fmp["revenueEstimateAvg"].notna().any()

                # Check if FMP has quarterly coverage (multiple quarters, not just annual)
                # FMP often only provides fiscal year-end data (Q3 for Apple)
                enriched_with_yq = False
                if has_revenue and 'endDate' in fmp.columns:
                    fmp_copy = fmp.copy()
                    fmp_copy['endDate'] = pd.to_datetime(fmp_copy['endDate'], errors='coerce')
                    # Extract quarters from dates
                    quarters = fmp_copy['endDate'].dropna().apply(lambda d: (d.month - 1) // 3 + 1 if hasattr(d, 'month') else None)
                    unique_quarters = quarters.unique()
                    has_quarterly_coverage = len(unique_quarters) > 1

                    if not has_quarterly_coverage:
                        logger.info("FMP returned annual data only (Q%s), trying to enrich with YahooQuery quarterly estimates...", unique_quarters[0] if len(unique_quarters) > 0 else 'unknown')
                        yq = self.get_analyst_estimates_yq(ticker)
                        if yq is not None and not yq.empty and 'revenueEstimateAvg' in yq.columns:
                            # Merge YahooQuery quarterly data with FMP annual data
                            fmp = merge_estimates_on_period_end(fmp, yq)
                            # Also try appending any non-overlapping quarters
                            if 'period' not in yq.columns and 'endDate' in yq.columns:
                                yq['period'] = yq['endDate'].apply(
                                    lambda d: f"{d.year}Q{((d.month - 1)//3)+1}" if pd.notna(d) and hasattr(d, 'year') else None
                                )
                            # Append YahooQuery rows that don't overlap with FMP dates
                            if 'endDate' in fmp.columns and 'endDate' in yq.columns:
                                fmp_dates = set(fmp['endDate'].astype(str))
                                yq_new = yq[~yq['endDate'].astype(str).isin(fmp_dates)]
                                if not yq_new.empty:
                                    fmp = pd.concat([fmp, yq_new], ignore_index=True, sort=False)
                                    logger.info("Enriched FMP data with %d quarterly estimates from YahooQuery", len(yq_new))
                                    enriched_with_yq = True

                logger.info(
                    "✓ Analyst estimates source selected for %s: %s (EPS: %s, Revenue: %s)",
                    ticker,
                    "FMP + YahooQuery enrichment" if enriched_with_yq else "FMP",
                    "yes" if has_eps else "no",
                    "yes" if has_revenue else "no",
                )
                return fmp
            else:
                logger.info("FMP: No data returned, trying next source...")

        # Step 2: Try Finnhub (EPS+revenue via company_estimates/fallback)
        if not self.finnhub_key:
            logger.info("Finnhub: Skipped (no API key configured)")
        else:
            logger.info("Finnhub: Trying...")
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

                # If still no revenue after Finnhub enrichment, try YahooQuery for revenue
                has_revenue = (
                    "revenueEstimateAvg" in fh.columns
                    and fh["revenueEstimateAvg"].notna().any()
                )

                if not has_revenue:
                    logger.info(
                        "Finnhub returned EPS estimates for %s but no revenue, trying YahooQuery for revenue",
                        ticker
                    )
                    yq = self.get_analyst_estimates_yq(ticker)
                    if yq is not None and not yq.empty and "revenueEstimateAvg" in yq.columns:
                        # Merge YahooQuery revenue estimates into Finnhub EPS estimates
                        fh = merge_estimates_on_period_end(fh, yq[["endDate", "revenueEstimateAvg"]])
                        has_revenue = "revenueEstimateAvg" in fh.columns and fh["revenueEstimateAvg"].notna().any()

                        # If merge didn't work (no matching dates), append YahooQuery data as new rows
                        if not has_revenue:
                            logger.info("Date-based merge failed, appending YahooQuery revenue data as separate rows")
                            # Add period column to yq if not present
                            if "period" not in yq.columns:
                                yq["period"] = yq["endDate"].apply(
                                    lambda d: f"{d.year}Q{((d.month - 1)//3)+1}" if pd.notna(d) and hasattr(d, "year") else None
                                )
                            fh = pd.concat([fh, yq], ignore_index=True, sort=False)
                            has_revenue = "revenueEstimateAvg" in fh.columns and fh["revenueEstimateAvg"].notna().any()

                logger.info(
                    "✓ Analyst estimates source selected for %s: %s%s",
                    ticker,
                    "Finnhub",
                    " + revenue_enriched" if has_revenue else " (EPS only, no revenue)",
                )
                return fh
            else:
                logger.info("Finnhub: No data returned, trying next source...")

        # Step 3: YahooQuery
        logger.info("YahooQuery: Trying (free source, no API key needed)...")
        yq = self.get_analyst_estimates_yq(ticker)
        if yq is not None and not yq.empty:
            has_eps = "epsEstimateAvg" in yq.columns and yq["epsEstimateAvg"].notna().any()
            has_revenue = "revenueEstimateAvg" in yq.columns and yq["revenueEstimateAvg"].notna().any()
            logger.info(
                "✓ Analyst estimates source selected for %s: %s (EPS: %s, Revenue: %s)",
                ticker,
                "YahooQuery",
                "yes" if has_eps else "no",
                "yes" if has_revenue else "no",
            )
            return yq
        else:
            logger.info("YahooQuery: No data returned, trying next source...")

        # Step 4: yfinance history (likely EPS only)
        logger.info("yfinance: Trying as last resort (free source, no API key needed)...")
        yf_hist = self.get_earnings_trend(ticker)
        if yf_hist is not None and not yf_hist.empty:
            logger.info(
                "✓ Analyst estimates source selected for %s: %s (likely EPS only)",
                ticker,
                "yfinance",
            )
            return yf_hist

        logger.warning("No analyst estimates found for %s from any source", ticker)
        return None
