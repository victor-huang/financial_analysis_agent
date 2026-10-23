"""Unit tests for FinancialDataFetcher intraday bar source selection."""
from datetime import datetime, timedelta

import pandas as pd
import pytest

from financial_analysis_agent.financial.data_fetcher import FinancialDataFetcher


def _bars(timestamps):
    return pd.DataFrame({"close": range(len(timestamps))}, index=pd.DatetimeIndex(timestamps))


@pytest.fixture
def fetcher(mocker):
    config = mocker.Mock()
    config.get.side_effect = lambda key, default=None: {
        "apis.alpaca.api_key": "key",
        "apis.alpaca.secret_key": "secret",
    }.get(key, default)
    mocker.patch("financial_analysis_agent.financial.data_fetcher.get_config", return_value=config)
    return FinancialDataFetcher()


class TestGetIntradayBars:
    def test_uses_alpaca_when_it_returns_bars(self, mocker, fetcher):
        alpaca_bars = _bars(["2026-07-30 04:00"])
        mocker.patch.object(fetcher.alpaca_source, "get_intraday_bars", return_value=alpaca_bars)
        yf_get = mocker.patch.object(fetcher._yfinance_source, "get_stock_data")

        df = fetcher.get_intraday_bars("AAPL", datetime(2026, 7, 30, 4), datetime(2026, 7, 30, 20))

        assert df is alpaca_bars
        yf_get.assert_not_called()

    def test_falls_back_to_yfinance_with_extended_hours_for_recent_windows(self, mocker, fetcher):
        start = (datetime.now() - timedelta(days=3)).replace(hour=4, minute=0, second=0, microsecond=0)
        end = start.replace(hour=20)
        mocker.patch.object(fetcher.alpaca_source, "get_intraday_bars", return_value=None)
        yf_get = mocker.patch.object(
            fetcher._yfinance_source,
            "get_stock_data",
            return_value=_bars([start - timedelta(hours=1), start, end, end + timedelta(hours=1)]),
        )

        df = fetcher.get_intraday_bars("AAPL", start, end)

        assert list(df.index) == [start, end]
        assert yf_get.call_args.kwargs["prepost"] is True
        assert yf_get.call_args.kwargs["interval"] == "5m"

    def test_returns_none_for_old_windows_when_alpaca_has_no_bars(self, mocker, fetcher):
        mocker.patch.object(fetcher.alpaca_source, "get_intraday_bars", return_value=None)
        yf_get = mocker.patch.object(fetcher._yfinance_source, "get_stock_data")

        df = fetcher.get_intraday_bars("AAPL", datetime(2025, 1, 2, 4), datetime(2025, 1, 2, 20))

        assert df is None
        yf_get.assert_not_called()

    def test_alpaca_source_is_none_without_credentials(self, mocker):
        config = mocker.Mock()
        config.get.return_value = None
        mocker.patch("financial_analysis_agent.financial.data_fetcher.get_config", return_value=config)

        assert FinancialDataFetcher().alpaca_source is None
