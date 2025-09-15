"""AlphaVantage data source module for retrieving financial data."""

import logging
from typing import Optional
import pandas as pd
from alpha_vantage.timeseries import TimeSeries

logger = logging.getLogger(__name__)


class AlphaVantageSource:
    """Class to fetch financial data from Alpha Vantage."""

    def __init__(self, api_key: str):
        """Initialize the Alpha Vantage data source.
        
        Args:
            api_key: Alpha Vantage API key
        """
        self.api_key = api_key
        self.client = TimeSeries(
            key=api_key, output_format="pandas", indexing_type="date"
        )

    def get_stock_data(
        self, ticker: str, interval: str = "1d"
    ) -> pd.DataFrame:
        """Get historical stock data for a given ticker.
        
        Args:
            ticker: Stock ticker symbol
            interval: Data interval ('1d', '1wk', '1mo')
            
        Returns:
            DataFrame with historical stock data
        """
        try:
            # Map interval to Alpha Vantage format
            interval_map = {"1d": "daily", "1wk": "weekly", "1mo": "monthly"}
            av_interval = interval_map.get(interval, "daily")

            if av_interval == "daily":
                data, _ = self.client.get_daily_adjusted(ticker, outputsize="full")
            elif av_interval == "weekly":
                data, _ = self.client.get_weekly_adjusted(ticker)
            elif av_interval == "monthly":
                data, _ = self.client.get_monthly_adjusted(ticker)

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
        except Exception as e:
            logger.error(f"Error fetching Alpha Vantage data for {ticker}: {str(e)}")
            raise
