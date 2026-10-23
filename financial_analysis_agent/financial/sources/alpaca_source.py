"""Alpaca data source module for retrieving historical intraday bars."""

import logging
from datetime import datetime
from typing import Optional

import pandas as pd
from alpaca.data.enums import Adjustment
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

logger = logging.getLogger(__name__)

MARKET_TIMEZONE = "America/New_York"


class AlpacaSource:
    """Class to fetch historical intraday stock bars from Alpaca.

    Alpaca bars include pre-market (04:00 ET) and after-hours (20:00 ET) sessions.
    """

    def __init__(self, api_key: str, secret_key: str, feed: str = "sip"):
        """Initialize the Alpaca data source.

        Args:
            api_key: Alpaca API key id
            secret_key: Alpaca secret key
            feed: Market data feed ('sip' for all US exchanges, 'iex' for IEX only)
        """
        self.api_key = api_key
        self.secret_key = secret_key
        self.feed = feed
        self._client = None

    @property
    def client(self):
        """Lazily initialize and return the Alpaca historical data client."""
        if self._client is None:
            try:
                self._client = StockHistoricalDataClient(self.api_key, self.secret_key)
                logger.info("Initialized Alpaca historical data client")
            except Exception as e:
                logger.warning(f"Alpaca client unavailable: {e}")
                return None
        return self._client

    def get_intraday_bars(
        self,
        ticker: str,
        start: datetime,
        end: datetime,
        interval_minutes: int = 5,
    ) -> Optional[pd.DataFrame]:
        """Fetch intraday bars, including extended trading hours.

        Args:
            ticker: Stock ticker symbol
            start: Start time (naive datetimes are treated as US/Eastern)
            end: End time (naive datetimes are treated as US/Eastern)
            interval_minutes: Bar size in minutes

        Returns:
            DataFrame indexed by naive US/Eastern bar start time with columns
            ['open', 'high', 'low', 'close', 'volume', 'trade_count', 'vwap'], or None.
        """
        client = self.client
        if client is None:
            return None

        try:
            request = StockBarsRequest(
                symbol_or_symbols=[ticker.replace("-", ".")],  # share classes: Alpaca uses BRK.B, Yahoo BRK-B
                timeframe=TimeFrame(amount=interval_minutes, unit=TimeFrameUnit.Minute),
                start=_to_market_time(start),
                end=_to_market_time(end),
                adjustment=Adjustment.ALL,
                feed=self.feed,
            )
            logger.info(f"Fetching {interval_minutes}-min bars from Alpaca for {ticker} from {start} to {end}")
            df = client.get_stock_bars(request).df
            if df is None or df.empty:
                logger.warning(f"No intraday bars from Alpaca for {ticker}")
                return None

            df = df.reset_index(level="symbol", drop=True)
            df.index = df.index.tz_convert(MARKET_TIMEZONE).tz_localize(None)
            df.index.name = "timestamp"
            return df
        except Exception as e:
            logger.error(f"Error fetching intraday bars from Alpaca for {ticker}: {e}")
            return None


def _to_market_time(value: datetime) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        return ts.tz_localize(MARKET_TIMEZONE)
    return ts.tz_convert(MARKET_TIMEZONE)
