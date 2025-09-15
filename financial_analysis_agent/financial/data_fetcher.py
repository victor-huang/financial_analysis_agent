"""Financial data fetcher module for retrieving financial data from various sources."""

import logging
from typing import Dict, List, Optional, Union
import pandas as pd
import yfinance as yf
from alpha_vantage.timeseries import TimeSeries
from datetime import datetime, timedelta

from ..config import get_config


logger = logging.getLogger(__name__)


# Helper to parse quarter labels like '2025Q2' or '2025-Q2' to quarter end dates
def _parse_quarter_end(period: Optional[str]) -> Optional[pd.Timestamp]:
    try:
        if not period or not isinstance(period, str):
            return pd.NaT
        s = period.strip().upper().replace(" ", "")
        # Accept forms like '2025Q2' or '2025-Q2'
        if "Q" in s:
            parts = s.replace("-", "")
            year = int(parts[:4])
            q = int(parts[5]) if len(parts) > 5 else int(parts.split("Q")[1])
            month_day = {1: (3, 31), 2: (6, 30), 3: (9, 30), 4: (12, 31)}.get(q)
            if month_day:
                month, day = month_day
                return pd.Timestamp(year=year, month=month, day=day)
        # Fallback: try generic parser
        return pd.to_datetime(s, errors="coerce")
    except Exception:
        return pd.NaT


# Merge helper: combine two estimate DataFrames on endDate/period, preferring exact date match then period label
def _merge_estimates_on_period_end(
    base: pd.DataFrame, rev: pd.DataFrame
) -> pd.DataFrame:
    try:
        b = base.copy()
        r = rev.copy()
        # Ensure datetime
        if "endDate" in b.columns:
            b["endDate"] = pd.to_datetime(b["endDate"], errors="coerce")
        if "endDate" in r.columns:
            r["endDate"] = pd.to_datetime(r["endDate"], errors="coerce")
        # First, exact endDate merge
        merged = pd.merge(
            b,
            r[["endDate", "revenueEstimateAvg"]]
            .dropna(subset=["endDate"])
            .drop_duplicates("endDate"),
            on="endDate",
            how="left",
            suffixes=("", "_rev"),
        )
        # If still missing revenueEstimateAvg, try period label join
        if ("revenueEstimateAvg" not in merged.columns) or (
            merged["revenueEstimateAvg"].isna().any()
        ):
            if "period" in b.columns and "period" in r.columns:
                merged2 = pd.merge(
                    merged,
                    r[["period", "revenueEstimateAvg"]]
                    .dropna(subset=["period"])
                    .drop_duplicates("period"),
                    on="period",
                    how="left",
                    suffixes=("", "_rev_period"),
                )
                # Fill missing with period-based
                if "revenueEstimateAvg_rev_period" in merged2.columns:
                    merged2["revenueEstimateAvg"] = merged2[
                        "revenueEstimateAvg"
                    ].combine_first(merged2["revenueEstimateAvg_rev_period"])
                    merged = merged2.drop(
                        columns=[
                            c for c in merged2.columns if c.endswith("_rev_period")
                        ]
                    )
        return merged
    except Exception as e:
        logger.warning(f"Failed to merge revenue estimates: {e}")
        return base


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
        # Finnhub (optional)
        self.finnhub_key = self.config.get("apis.finnhub.api_key") or self.config.get(
            "FINNHUB_API_KEY"
        )
        self._finnhub_client = None

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

    def get_earnings_dates(self, ticker: str, limit: int = 8) -> Optional[pd.DataFrame]:
        """Get recent earnings dates with EPS estimates/actuals/surprise.

        Returns a DataFrame indexed by announcement date with columns like:
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

        The structure returned by yfinance can vary; we'll try to coerce to a DataFrame
        with columns including 'period', 'endDate', 'epsEstimateAvg', 'revenueEstimateAvg'.
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

    def get_analyst_estimates_yq(self, ticker: str) -> Optional[pd.DataFrame]:
        """Fetch analyst EPS and revenue estimates per quarter using yahooquery.

        Returns a DataFrame with columns: ['period', 'endDate', 'epsEstimateAvg', 'revenueEstimateAvg'].
        """
        try:
            from yahooquery import Ticker as YQTicker
        except Exception as imp_err:
            logger.warning(f"yahooquery not available: {imp_err}")
            return None

        try:
            yq = YQTicker(ticker)
            data = yq.earnings_trend
            # data can be a dict keyed by ticker, or already the structure
            if isinstance(data, dict) and ticker in data:
                node = data.get(ticker) or {}
            else:
                node = data or {}

            trend = None
            if isinstance(node, dict):
                trend = node.get("trend") or node.get("trends")
            elif isinstance(node, list):
                trend = node

            if not trend:
                logger.warning("yahooquery returned no earnings trend")
                return None

            # Normalize to DataFrame
            try:
                tdf = pd.DataFrame(trend)
            except Exception:
                return None

            # Extract nested estimates if present
            def _nested_avg(series: pd.Series, key: str) -> Optional[pd.Series]:
                try:
                    return series.apply(
                        lambda x: (x or {}).get(key) if isinstance(x, dict) else None
                    )
                except Exception:
                    return None

            if "earningsEstimate" in tdf.columns and "avg" not in tdf.columns:
                tdf["epsEstimateAvg"] = pd.to_numeric(
                    _nested_avg(tdf["earningsEstimate"], "avg"), errors="coerce"
                )
            # Some schemas may expose 'salesEstimate' instead of 'revenueEstimate'
            if "revenueEstimate" in tdf.columns and "avg" not in tdf.columns:
                tdf["revenueEstimateAvg"] = pd.to_numeric(
                    _nested_avg(tdf["revenueEstimate"], "avg"), errors="coerce"
                )
            elif "salesEstimate" in tdf.columns:
                tdf["revenueEstimateAvg"] = pd.to_numeric(
                    _nested_avg(tdf["salesEstimate"], "avg"), errors="coerce"
                )

            # endDate and period
            if "endDate" in tdf.columns:
                tdf["endDate"] = pd.to_datetime(tdf["endDate"], errors="coerce")
            elif "period" in tdf.columns:
                # try direct parse, then fall back to quarter-end parsing
                tdf["endDate"] = pd.to_datetime(tdf["period"], errors="coerce")
                if tdf["endDate"].isna().any():
                    tdf["endDate"] = tdf.apply(
                        lambda r: _parse_quarter_end(str(r.get("period"))), axis=1
                    )

            keep_cols = [
                c
                for c in ["period", "endDate", "epsEstimateAvg", "revenueEstimateAvg"]
                if c in tdf.columns
            ]
            if not keep_cols:
                return None
            out = (
                tdf[keep_cols].dropna(subset=["endDate"])
                if "endDate" in keep_cols
                else tdf[keep_cols]
            )
            if "endDate" in out.columns:
                out = out.sort_values("endDate", ascending=False)
            return out
        except Exception as e:
            logger.error(
                f"Error fetching analyst estimates from yahooquery for {ticker}: {e}"
            )
            return None

    def _ensure_finnhub(self):
        """Lazily create Finnhub client if API key is configured."""
        if self._finnhub_client is not None:
            return self._finnhub_client
        if not self.finnhub_key:
            return None
        try:
            import finnhub

            self._finnhub_client = finnhub.Client(api_key=self.finnhub_key)
            logger.info("Initialized Finnhub client for analyst estimates fetching")
            return self._finnhub_client
        except Exception as e:
            logger.warning(f"Finnhub client unavailable: {e}")
            return None

    def get_analyst_estimates_finnhub(
        self, ticker: str, limit: int = 8
    ) -> Optional[pd.DataFrame]:
        """Fetch quarterly analyst estimates (EPS and revenue) from Finnhub.

        Normalizes to columns: ['period', 'endDate', 'epsEstimateAvg', 'revenueEstimateAvg'].
        """
        client = self._ensure_finnhub()
        if client is None:
            return None
        try:
            logger.info(f"Fetching analyst estimates from Finnhub for {ticker}")
            # First preference: company_estimates (quarterly)
            df = None
            if hasattr(client, "company_estimates"):
                try:
                    ce = client.company_estimates(symbol=ticker)
                    try:
                        # Log basic structure of the raw payload
                        if isinstance(ce, dict):
                            logger.info(
                                f"Finnhub company_estimates raw keys for {ticker}: {list(ce.keys())}"
                            )
                        else:
                            logger.info(
                                f"Finnhub company_estimates returned type {type(ce)} for {ticker}"
                            )
                    except Exception:
                        pass
                    # Expected structure: {'symbol': 'AAPL', 'data': [...]} or just list in some versions
                    rows = None
                    if isinstance(ce, dict):
                        rows = ce.get("data") or ce.get("estimates") or ce.get("Result")
                    elif isinstance(ce, list):
                        rows = ce
                    if rows:
                        df = pd.DataFrame(rows)
                        try:
                            logger.info(
                                f"Finnhub company_estimates columns for {ticker}: {list(df.columns)}"
                            )
                            logger.info(
                                f"Finnhub company_estimates sample rows for {ticker}: {df.head(5).to_dict(orient='records')}"
                            )
                        except Exception:
                            pass
                        # Normalize keys: period, endDate, epsAvg, revenueAvg
                        out = pd.DataFrame()
                        if "period" in df.columns:
                            out["period"] = df["period"].astype(str)
                        elif {"year", "quarter"}.issubset(df.columns):
                            out["period"] = df.apply(
                                lambda r: f"{int(r['year'])}Q{int(r['quarter'])}",
                                axis=1,
                            )
                        # End date
                        if "period" in out.columns:
                            out["endDate"] = pd.to_datetime(
                                out["period"], errors="coerce"
                            )
                            if out["endDate"].isna().any():
                                out["endDate"] = out["period"].apply(
                                    lambda s: _parse_quarter_end(str(s))
                                )
                        elif "date" in df.columns:
                            out["endDate"] = pd.to_datetime(df["date"], errors="coerce")
                        # Estimates
                        if "epsAvg" in df.columns:
                            out["epsEstimateAvg"] = pd.to_numeric(
                                df["epsAvg"], errors="coerce"
                            )
                        elif "epsEstimate" in df.columns:
                            out["epsEstimateAvg"] = pd.to_numeric(
                                df["epsEstimate"], errors="coerce"
                            )
                        # EPS actual when available
                        if "epsActual" in df.columns:
                            out["epsActual"] = pd.to_numeric(
                                df["epsActual"], errors="coerce"
                            )
                        if "revenueAvg" in df.columns:
                            out["revenueEstimateAvg"] = pd.to_numeric(
                                df["revenueAvg"], errors="coerce"
                            )
                        elif "revenueEstimate" in df.columns:
                            out["revenueEstimateAvg"] = pd.to_numeric(
                                df["revenueEstimate"], errors="coerce"
                            )
                        # Sort and return if we have useful columns
                        if "endDate" in out.columns:
                            out = out.dropna(subset=["endDate"]).sort_values(
                                "endDate", ascending=False
                            )
                        keep = [
                            c
                            for c in [
                                "period",
                                "endDate",
                                "epsEstimateAvg",
                                "revenueEstimateAvg",
                            ]
                            if c in out.columns
                        ]
                        if keep:
                            result = out[keep]
                            logger.info(
                                f"Finnhub company_estimates returned {len(result)} rows for {ticker}"
                            )
                            return result
                except Exception as e:
                    logger.info(
                        f"Finnhub company_estimates not available for {ticker}: {e}"
                    )

            # Fallback: older/general earnings endpoints (may not include revenue estimates)
            data = None
            for method_name in ["company_earnings", "earnings"]:
                if hasattr(client, method_name):
                    try:
                        fn = getattr(client, method_name)
                        data = fn(symbol=ticker, limit=limit)
                        break
                    except TypeError:
                        try:
                            data = getattr(client, method_name)(symbol=ticker)
                            break
                        except Exception:
                            continue
            if data is None:
                return None
            rows = data if isinstance(data, list) else data.get("earnings") or []
            if not rows:
                return None
            df = pd.DataFrame(rows)
            try:
                logger.info(
                    f"Finnhub fallback earnings columns for {ticker}: {list(df.columns)}"
                )
                logger.info(
                    f"Finnhub fallback earnings sample rows for {ticker}: {df.head(5).to_dict(orient='records')}"
                )
            except Exception:
                pass
            out = pd.DataFrame()
            if "period" in df.columns:
                out["period"] = df["period"].astype(str)
            elif {"year", "quarter"}.issubset(df.columns):
                out["period"] = df.apply(
                    lambda r: f"{int(r['year'])}Q{int(r['quarter'])}", axis=1
                )
            if "date" in df.columns:
                out["endDate"] = pd.to_datetime(df["date"], errors="coerce")
            elif "period" in out.columns:
                out["endDate"] = pd.to_datetime(out["period"], errors="coerce")
                if out["endDate"].isna().any():
                    out["endDate"] = out["period"].apply(
                        lambda s: _parse_quarter_end(str(s))
                    )
            # EPS estimates
            if "epsEstimate" in df.columns:
                out["epsEstimateAvg"] = pd.to_numeric(
                    df["epsEstimate"], errors="coerce"
                )
            elif "estimate" in df.columns:
                # Some Finnhub fallback endpoints use generic 'estimate' for EPS
                out["epsEstimateAvg"] = pd.to_numeric(df["estimate"], errors="coerce")
            # EPS actual
            if "epsActual" in df.columns:
                out["epsActual"] = pd.to_numeric(df["epsActual"], errors="coerce")
            elif "actual" in df.columns:
                out["epsActual"] = pd.to_numeric(df["actual"], errors="coerce")
            # Revenue estimates likely missing in this fallback
            if "endDate" in out.columns:
                out = out.dropna(subset=["endDate"]).sort_values(
                    "endDate", ascending=False
                )
            keep = [
                c
                for c in ["period", "endDate", "epsEstimateAvg", "revenueEstimateAvg"]
                if c in out.columns
            ]
            result = out[keep] if keep else None
            if result is not None:
                logger.info(
                    f"Finnhub fallback earnings returned {len(result)} rows for {ticker}"
                )
            return result
        except Exception as e:
            logger.error(
                f"Error fetching analyst estimates from Finnhub for {ticker}: {e}"
            )
            return None

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
                    fh = _merge_estimates_on_period_end(fh, rev)
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

    def get_revenue_estimates_finnhub(self, ticker: str) -> Optional[pd.DataFrame]:
        """Call Finnhub company-revenue-estimates API and normalize.

        Returns DataFrame with ['period','endDate','revenueEstimateAvg'] when possible.
        """
        client = self._ensure_finnhub()
        if client is None:
            return None
        try:
            rows = None
            for method_name in ["company_revenue_estimates", "revenue_estimates"]:
                if hasattr(client, method_name):
                    try:
                        fn = getattr(client, method_name)
                        payload = fn(symbol=ticker, freq="quarterly")
                        # Finnhub typically returns {'symbol': 'AAPL', 'freq': 'quarterly', 'data': [...]}
                        if isinstance(payload, dict):
                            rows = (
                                payload.get("data")
                                or payload.get("estimates")
                                or payload.get("Result")
                            )
                        elif isinstance(payload, list):
                            rows = payload
                        logger.info(
                            "Finnhub revenue estimates raw keys for %s: %s",
                            ticker,
                            (
                                list(payload.keys())
                                if isinstance(payload, dict)
                                else type(payload)
                            ),
                        )
                        break
                    except Exception as e:
                        logger.info(
                            "Finnhub %s not available for %s: %s",
                            method_name,
                            ticker,
                            e,
                        )
                        continue
            if not rows:
                return None
            df = pd.DataFrame(rows)
            try:
                logger.info(
                    "Finnhub revenue estimates columns for %s: %s",
                    ticker,
                    list(df.columns),
                )
                logger.info(
                    "Finnhub revenue estimates sample rows for %s: %s",
                    ticker,
                    df.head(5).to_dict(orient="records"),
                )
            except Exception:
                pass
            out = pd.DataFrame()
            # Period label
            if "period" in df.columns:
                out["period"] = df["period"].astype(str)
            elif {"year", "quarter"}.issubset(df.columns):
                out["period"] = df.apply(
                    lambda r: f"{int(r['year'])}Q{int(r['quarter'])}", axis=1
                )
            elif "timePeriod" in df.columns:
                out["period"] = df["timePeriod"].astype(str)
            # End date
            if "period" in out.columns:
                out["endDate"] = pd.to_datetime(out["period"], errors="coerce")
                if out["endDate"].isna().any():
                    out["endDate"] = out["period"].apply(
                        lambda s: _parse_quarter_end(str(s))
                    )
            elif "date" in df.columns:
                out["endDate"] = pd.to_datetime(df["date"], errors="coerce")
            # Revenue estimate keys
            for key in [
                "revenueAvg",
                "revenueEstimate",
                "revenueMean",
                "salesAvg",
                "salesEstimate",
                "salesMean",
                "estimate",
            ]:
                if key in df.columns:
                    out["revenueEstimateAvg"] = pd.to_numeric(df[key], errors="coerce")
                    break
            if "endDate" in out.columns:
                out = out.dropna(subset=["endDate"]).sort_values(
                    "endDate", ascending=False
                )
            keep = [
                c
                for c in ["period", "endDate", "revenueEstimateAvg"]
                if c in out.columns
            ]
            return out[keep] if keep else None
        except Exception as e:
            logger.error(
                "Error fetching Finnhub revenue estimates for %s: %s", ticker, e
            )
            return None
