"""Financial data fetcher module for retrieving financial data from various sources."""

import logging
from typing import Dict, List, Optional, Union
import pandas as pd
import yfinance as yf
from alpha_vantage.timeseries import TimeSeries
from datetime import datetime, timedelta

from ..config import get_config

logger = logging.getLogger(__name__)


class FinancialDataFetcher:
    """Class to fetch financial data from various sources."""

    def __init__(self, api_key: str = None):
        """Initialize the financial data fetcher.

        Args:
            api_key: Alpha Vantage API key. If not provided, will try to get from config.
        """
        self.config = get_config()
        self.alpha_vantage_key = api_key or self.config.get(
            "apis.alpha_vantage.api_key"
        )
        self.alpha_vantage = None

        if self.alpha_vantage_key:
            self.alpha_vantage = TimeSeries(
                key=self.alpha_vantage_key, output_format="pandas", indexing_type="date"
            )

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

        Returns:
            DataFrame with historical stock data
        """
        if start_date is None and period is None:
            start_date = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
        if end_date is None and period is None:
            end_date = datetime.now().strftime("%Y-%m-%d")

        if isinstance(start_date, datetime):
            start_date = start_date.strftime("%Y-%m-%d")
        if isinstance(end_date, datetime):
            end_date = end_date.strftime("%Y-%m-%d")

        logger.info(f"Fetching {ticker} data from {start_date} to {end_date}")

        try:
            if source.lower() == "yfinance":
                return self._get_yfinance_data(
                    ticker, start_date, end_date, interval, period=period
                )
            elif source.lower() == "alpha_vantage":
                return self._get_alpha_vantage_data(ticker, interval)
            else:
                raise ValueError(f"Unsupported data source: {source}")
        except Exception as e:
            logger.error(f"Error fetching stock data for {ticker}: {str(e)}")
            raise

    def _get_yfinance_data(
        self,
        ticker: str,
        start_date: Optional[str],
        end_date: Optional[str],
        interval: str = "1d",
        period: Optional[str] = None,
    ) -> pd.DataFrame:
        """Get data from Yahoo Finance."""
        stock = yf.Ticker(ticker)
        if period:
            df = stock.history(period=period, interval=interval, auto_adjust=True)
        else:
            df = stock.history(
                start=start_date, end=end_date, interval=interval, auto_adjust=True
            )

        # Clean up the dataframe
        if not df.empty:
            df.index = pd.to_datetime(df.index)
            df = df.tz_localize(None)  # Remove timezone info
            df = df.rename(
                columns={
                    "Open": "open",
                    "High": "high",
                    "Low": "low",
                    "Close": "close",
                    "Volume": "volume",
                    "Dividends": "dividends",
                    "Stock Splits": "splits",
                }
            )

        return df

    def _get_alpha_vantage_data(
        self, ticker: str, interval: str = "1d"
    ) -> pd.DataFrame:
        """Get data from Alpha Vantage."""
        if not self.alpha_vantage:
            raise ValueError("Alpha Vantage API key not configured")

        # Map interval to Alpha Vantage format
        interval_map = {"1d": "daily", "1wk": "weekly", "1mo": "monthly"}

        av_interval = interval_map.get(interval, "daily")

        if av_interval == "daily":
            data, _ = self.alpha_vantage.get_daily_adjusted(ticker, outputsize="full")
        elif av_interval == "weekly":
            data, _ = self.alpha_vantage.get_weekly_adjusted(ticker)
        elif av_interval == "monthly":
            data, _ = self.alpha_vantage.get_monthly_adjusted(ticker)

        # Clean up the dataframe
        data.index = pd.to_datetime(data.index)
        data = data.rename(
            columns={
                "1. open": "open",
                "2. high": "high",
                "3. low": "low",
                "4. close": "close",
                "5. adjusted close": "adj_close",
                "6. volume": "volume",
                "7. dividend amount": "dividend",
                "8. split coefficient": "split_coefficient",
            }
        )

        return data

    def get_company_info(self, ticker: str) -> Dict:
        """Get company information."""
        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            return {
                "name": info.get("shortName", ""),
                "sector": info.get("sector", ""),
                "industry": info.get("industry", ""),
                "market_cap": info.get("marketCap"),
                "description": info.get("longBusinessSummary", ""),
                "website": info.get("website", ""),
                "employees": info.get("fullTimeEmployees"),
                "country": info.get("country", ""),
            }
        except Exception as e:
            logger.error(f"Error fetching company info for {ticker}: {str(e)}")
            return {}

    def get_company_news(self, ticker: str, limit: int = 10) -> List[Dict]:
        """Get recent news articles about the company."""
        try:
            stock = yf.Ticker(ticker)
            news = stock.news
            return [
                {
                    "title": item.get("title", ""),
                    "publisher": item.get("publisher", ""),
                    "link": item.get("link", ""),
                    "published_at": item.get("providerPublishTime", ""),
                    "summary": item.get("summary", ""),
                }
                for item in news[:limit]
            ]
        except Exception as e:
            logger.error(f"Error fetching news for {ticker}: {str(e)}")
            return []

    def get_financials(
        self,
        ticker: str,
        statement_type: str = "income",
        period: str = "annual",
        limit: int = 4,
    ) -> Optional[pd.DataFrame]:
        """Get financial statements.

        Args:
            ticker: Stock ticker symbol
            statement_type: Type of financial statement ('income', 'balance', 'cashflow')
            period: 'annual' or 'quarterly'
            limit: Number of periods to return

        Returns:
            DataFrame with financial statement data
        """
        try:
            stock = yf.Ticker(ticker)

            if statement_type == "income":
                if period == "annual":
                    return stock.financials.T.head(limit)
                else:
                    return stock.quarterly_financials.T.head(limit)
            elif statement_type == "balance":
                if period == "annual":
                    return stock.balance_sheet.T.head(limit)
                else:
                    return stock.quarterly_balance_sheet.T.head(limit)
            elif statement_type == "cashflow":
                if period == "annual":
                    return stock.cashflow.T.head(limit)
                else:
                    return stock.quarterly_cashflow.T.head(limit)
            else:
                raise ValueError(f"Unsupported statement type: {statement_type}")

        except Exception as e:
            logger.error(
                f"Error fetching {statement_type} statement for {ticker}: {str(e)}"
            )
            return None
