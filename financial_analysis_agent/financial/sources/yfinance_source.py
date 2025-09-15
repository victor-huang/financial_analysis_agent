"""YFinance data source module for retrieving financial data."""

import logging
from typing import Dict, List, Optional, Union
from datetime import datetime, timedelta
import pandas as pd
import yfinance as yf

from ..utils.date_utils import parse_quarter_end

logger = logging.getLogger(__name__)


class YFinanceSource:
    """Class to fetch financial data from Yahoo Finance."""

    def get_stock_data(
        self,
        ticker: str,
        start_date: Union[str, datetime] = None,
        end_date: Union[str, datetime] = None,
        interval: str = "1d",
        period: Optional[str] = None,
    ) -> pd.DataFrame:
        """Get historical stock data for a given ticker.

        Args:
            ticker: Stock ticker symbol
            start_date: Start date for data (default: 1 year ago)
            end_date: End date for data (default: today)
            interval: Data interval ('1d', '1wk', '1mo')
            period: Alternative to start/end date, e.g., '1y', '6mo'

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
        except Exception as e:
            logger.error(f"Error fetching stock data for {ticker}: {str(e)}")
            raise

    def get_company_info(self, ticker: str) -> Dict:
        """Get company information.
        
        Args:
            ticker: Stock ticker symbol
            
        Returns:
            Dictionary with company information
        """
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
        """Get recent news articles about the company.
        
        Args:
            ticker: Stock ticker symbol
            limit: Maximum number of news items to return
            
        Returns:
            List of dictionaries with news information
        """
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

    def get_earnings_dates(self, ticker: str, limit: int = 8) -> Optional[pd.DataFrame]:
        """Get recent earnings dates with EPS estimates/actuals/surprise.

        Args:
            ticker: Stock ticker symbol
            limit: Maximum number of earnings dates to return
            
        Returns:
            DataFrame indexed by announcement date with columns like:
            ['EPS Estimate', 'Reported EPS', 'Surprise', 'Surprise(%)'] when available.
        """
        try:
            stock = yf.Ticker(ticker)
            # yfinance provides get_earnings_dates(limit=...)
            df = stock.get_earnings_dates(limit=limit)
            if df is None or df.empty:
                return None
            # normalize index to datetime (announcement date)
            df.index = pd.to_datetime(df.index)
            df = df.sort_index(ascending=False)
            return df
        except Exception as e:
            logger.error(f"Error fetching earnings dates for {ticker}: {str(e)}")
            return None

    def get_earnings_trend(self, ticker: str) -> Optional[pd.DataFrame]:
        """Get earnings trend which may include quarterly EPS and revenue estimates.

        Args:
            ticker: Stock ticker symbol
            
        Returns:
            DataFrame with columns including 'period', 'endDate', 'epsEstimateAvg', 'revenueEstimateAvg'.
        """
        try:
            stock = yf.Ticker(ticker)
            if not hasattr(stock, "get_earnings_history"):
                logger.warning(
                    "yfinance Ticker has no get_earnings_history(); no earnings trend available"
                )
                return None

            hist = stock.get_earnings_history()
            # Normalize to DataFrame
            if isinstance(hist, pd.DataFrame):
                if hist.empty:
                    return None
                dfh = hist.copy()
            elif isinstance(hist, (list, tuple)) and len(hist) > 0:
                dfh = pd.DataFrame(hist)
            else:
                return None

            # Map common fields to normalized columns
            cols: Dict[str, pd.Series] = {}
            if "startdatetime" in dfh.columns:
                cols["endDate"] = pd.to_datetime(dfh["startdatetime"], errors="coerce")
            elif "startDate" in dfh.columns:
                cols["endDate"] = pd.to_datetime(dfh["startDate"], errors="coerce")

            if "epsestimate" in dfh.columns:
                cols["epsEstimateAvg"] = pd.to_numeric(
                    dfh["epsestimate"], errors="coerce"
                )
            if "revenueestimate" in dfh.columns:
                cols["revenueEstimateAvg"] = pd.to_numeric(
                    dfh["revenueestimate"], errors="coerce"
                )

            if "quarter" in dfh.columns:
                cols["period"] = dfh["quarter"].astype(str)

            if not cols:
                logger.warning("No mappable fields in earnings history")
                return None

            trend = pd.DataFrame(cols)
            # Clean and sort
            if "endDate" in trend.columns:
                trend = trend.dropna(subset=["endDate"]).sort_values(
                    "endDate", ascending=False
                )

            keep_cols = [
                c
                for c in ["period", "endDate", "epsEstimateAvg", "revenueEstimateAvg"]
                if c in trend.columns
            ]
            return trend[keep_cols] if keep_cols else trend
        except Exception as e:
            logger.error(f"Error fetching earnings trend for {ticker}: {str(e)}")
            return None
