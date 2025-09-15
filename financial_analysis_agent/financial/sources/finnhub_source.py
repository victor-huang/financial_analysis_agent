"""Finnhub data source module for retrieving financial data."""

import logging
from typing import Dict, List, Optional
import pandas as pd

from ..utils.date_utils import parse_quarter_end

logger = logging.getLogger(__name__)


class FinnhubSource:
    """Class to fetch financial data from Finnhub."""

    def __init__(self, api_key: str):
        """Initialize the Finnhub data source.
        
        Args:
            api_key: Finnhub API key
        """
        self.api_key = api_key
        self._client = None

    @property
    def client(self):
        """Lazily initialize and return the Finnhub client."""
        if self._client is None:
            try:
                import finnhub
                self._client = finnhub.Client(api_key=self.api_key)
                logger.info("Initialized Finnhub client for analyst estimates fetching")
            except Exception as e:
                logger.warning(f"Finnhub client unavailable: {e}")
                return None
        return self._client

    def get_analyst_estimates(self, ticker: str, limit: int = 8) -> Optional[pd.DataFrame]:
        """Fetch quarterly analyst estimates (EPS) from Finnhub.
        
        Args:
            ticker: Stock ticker symbol
            limit: Maximum number of estimates to return
            
        Returns:
            DataFrame with normalized columns: ['period', 'endDate', 'epsEstimateAvg', 'epsActual']
        """
        client = self.client
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
                        rows = (
                            ce.get("data") 
                            or ce.get("estimates") 
                            or ce.get("Result")
                        )
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
                            out["endDate"] = pd.to_datetime(out["period"], errors="coerce")
                            if out["endDate"].isna().any():
                                out["endDate"] = out["period"].apply(
                                    lambda s: parse_quarter_end(str(s))
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
                                "epsActual",
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
                        lambda s: parse_quarter_end(str(s))
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
                for c in ["period", "endDate", "epsEstimateAvg", "epsActual", "revenueEstimateAvg"]
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

    def get_revenue_estimates(self, ticker: str) -> Optional[pd.DataFrame]:
        """Call Finnhub company-revenue-estimates API and normalize.
        
        Args:
            ticker: Stock ticker symbol
            
        Returns:
            DataFrame with ['period','endDate','revenueEstimateAvg'] when possible.
        """
        client = self.client
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
                        lambda s: parse_quarter_end(str(s))
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
