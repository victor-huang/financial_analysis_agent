"""YahooQuery data source module for retrieving financial data."""

import logging
from typing import Optional
import pandas as pd

from ..utils.date_utils import parse_quarter_end

logger = logging.getLogger(__name__)


class YahooQuerySource:
    """Class to fetch financial data from Yahoo Query."""

    def get_analyst_estimates(self, ticker: str) -> Optional[pd.DataFrame]:
        """Fetch analyst EPS and revenue estimates per quarter using yahooquery.
        
        Args:
            ticker: Stock ticker symbol
            
        Returns:
            DataFrame with columns: ['period', 'endDate', 'epsEstimateAvg', 'revenueEstimateAvg'].
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
                        lambda r: parse_quarter_end(str(r.get("period"))), axis=1
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
