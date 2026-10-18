"""Unit tests for AlpacaSource intraday bars."""
from datetime import datetime

import pandas as pd

from financial_analysis_agent.financial.sources.alpaca_source import AlpacaSource


def _alpaca_bars_df():
    index = pd.MultiIndex.from_tuples(
        [
            ("AAPL", pd.Timestamp("2026-07-30 08:00", tz="UTC")),
            ("AAPL", pd.Timestamp("2026-07-30 20:05", tz="UTC")),
        ],
        names=["symbol", "timestamp"],
    )
    return pd.DataFrame(
        {"open": [1.0, 2.0], "high": [1.0, 2.0], "low": [1.0, 2.0], "close": [1.0, 2.0],
         "volume": [10.0, 20.0], "trade_count": [1.0, 2.0], "vwap": [1.0, 2.0]},
        index=index,
    )


def _source_with_client(mocker, bars_df=None, side_effect=None):
    client = mocker.Mock()
    client.get_stock_bars.return_value = mocker.Mock(df=bars_df)
    client.get_stock_bars.side_effect = side_effect
    source = AlpacaSource("key", "secret", feed="sip")
    source._client = client
    return source, client


class TestGetIntradayBars:
    def test_returns_bars_indexed_by_naive_eastern_time(self, mocker):
        source, _ = _source_with_client(mocker, _alpaca_bars_df())

        df = source.get_intraday_bars("AAPL", datetime(2026, 7, 30, 4), datetime(2026, 7, 30, 20))

        assert list(df.index) == [pd.Timestamp("2026-07-30 04:00"), pd.Timestamp("2026-07-30 16:05")]
        assert df.index.name == "timestamp"
        assert "symbol" not in df.index.names

    def test_treats_naive_times_as_eastern_and_requests_configured_feed(self, mocker):
        source, client = _source_with_client(mocker, _alpaca_bars_df())

        source.get_intraday_bars("AAPL", datetime(2026, 7, 30, 4), datetime(2026, 7, 30, 20), interval_minutes=5)

        request = client.get_stock_bars.call_args.args[0]
        assert request.start == pd.Timestamp("2026-07-30 08:00")  # alpaca-py normalizes to naive UTC
        assert request.end == pd.Timestamp("2026-07-31 00:00")
        assert request.feed.value == "sip"
        assert request.timeframe.amount == 5

    def test_returns_none_when_no_bars(self, mocker):
        source, _ = _source_with_client(mocker, pd.DataFrame())

        assert source.get_intraday_bars("AAPL", datetime(2026, 7, 30, 4), datetime(2026, 7, 30, 20)) is None

    def test_returns_none_when_api_errors(self, mocker):
        source, _ = _source_with_client(mocker, side_effect=RuntimeError("forbidden"))

        assert source.get_intraday_bars("AAPL", datetime(2026, 7, 30, 4), datetime(2026, 7, 30, 20)) is None

    def test_returns_none_when_client_unavailable(self, mocker):
        source = AlpacaSource("key", "secret")
        mocker.patch.object(AlpacaSource, "client", new_callable=mocker.PropertyMock, return_value=None)

        assert source.get_intraday_bars("AAPL", datetime(2026, 7, 30, 4), datetime(2026, 7, 30, 20)) is None
