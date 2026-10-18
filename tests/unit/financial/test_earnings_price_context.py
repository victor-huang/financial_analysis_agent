"""Unit tests for EarningsPriceContextCollector."""
import json
from datetime import date, datetime, timedelta

import pandas as pd
import pytest

from financial_analysis_agent.financial.earnings_price_context import (
    EarningsEvent,
    EarningsPriceContextCollector,
    _reaction_position,
)

AS_OF = date(2026, 10, 16)
SESSIONS = pd.bdate_range("2025-06-02", "2026-10-16")


def _daily_bars(base_close: float, step: float = 0.0) -> pd.DataFrame:
    closes = [base_close + step * i for i in range(len(SESSIONS))]
    return pd.DataFrame(
        {"open": closes, "high": [c + 1 for c in closes], "low": [c - 1 for c in closes],
         "close": closes, "volume": [1000] * len(SESSIONS)},
        index=SESSIONS,
    )


def _fmp_calendar(rows):
    df = pd.DataFrame(rows)
    df["announceDate"] = pd.to_datetime(df["announceDate"])
    return df


@pytest.fixture
def fetcher(mocker):
    fetcher = mocker.Mock()
    bars = {"AAPL": _daily_bars(100.0), "XLK": _daily_bars(50.0), "SPY": _daily_bars(500.0)}
    fetcher.get_stock_data.side_effect = lambda symbol, **kwargs: bars[symbol].copy()
    fetcher.get_company_info.return_value = {"sector": "Technology"}
    fetcher.get_historical_earnings_calendar_fmp.return_value = _fmp_calendar(
        [
            {"announceDate": "2026-11-02", "releaseTime": "amc", "epsEstimate": 1.99, "epsActual": None},
            {"announceDate": "2026-07-30", "releaseTime": "amc", "epsEstimate": 1.89, "epsActual": 2.02},
            {"announceDate": "2026-04-29", "releaseTime": "bmo", "epsEstimate": 1.6, "epsActual": 1.7},
        ]
    )
    fetcher.get_intraday_bars.return_value = pd.DataFrame(
        {"close": [1.0]}, index=pd.DatetimeIndex(["2026-07-31 09:30"], name="timestamp")
    )
    return fetcher


@pytest.fixture
def collector(fetcher, tmp_path):
    return EarningsPriceContextCollector(fetcher=fetcher, output_dir=str(tmp_path), as_of=AS_OF)


class TestResolveEarningsEvents:
    def test_splits_reported_and_upcoming_releases(self, collector):
        past, upcoming = collector.resolve_earnings_events("AAPL")

        assert [e.release_date for e in past] == [date(2026, 7, 30), date(2026, 4, 29)]
        assert upcoming.release_date == date(2026, 11, 2)

    def test_limits_past_releases_to_requested_quarters(self, collector):
        past, _ = collector.resolve_earnings_events("AAPL", num_quarters=1)

        assert [e.release_date for e in past] == [date(2026, 7, 30)]

    def test_uses_fmp_release_timing(self, collector):
        past, _ = collector.resolve_earnings_events("AAPL")

        assert [e.timing for e in past] == ["amc", "bmo"]

    def test_falls_back_to_yfinance_without_fmp_data(self, collector, fetcher):
        fetcher.get_historical_earnings_calendar_fmp.return_value = None
        fetcher.get_earnings_dates.return_value = pd.DataFrame(
            {"EPS Estimate": [1.6, None, 1.3], "Reported EPS": [1.65, None, 1.4],
             "Event Type": ["Earnings", "Meeting", "Earnings"]},
            index=pd.DatetimeIndex(
                ["2026-05-01 16:30", "2026-02-27 12:00", "2026-01-30 07:00"], tz="America/New_York"
            ),
        )

        past, upcoming = collector.resolve_earnings_events("AAPL")

        assert [(e.release_date, e.timing) for e in past] == [
            (date(2026, 5, 1), "amc"),
            (date(2026, 1, 30), "bmo"),
        ]
        assert upcoming is None


class TestReactionPosition:
    def test_before_open_release_reacts_on_release_date(self):
        pos = _reaction_position(SESSIONS, EarningsEvent(date(2026, 7, 30), "bmo"))

        assert SESSIONS[pos].date() == date(2026, 7, 30)

    def test_after_close_release_reacts_next_session(self):
        pos = _reaction_position(SESSIONS, EarningsEvent(date(2026, 7, 31), "amc"))

        assert SESSIONS[pos].date() == date(2026, 8, 3)

    def test_weekend_release_reacts_on_next_session(self):
        pos = _reaction_position(SESSIONS, EarningsEvent(date(2026, 8, 1), "amc"))

        assert SESSIONS[pos].date() == date(2026, 8, 3)

    def test_returns_none_when_reaction_session_not_yet_traded(self):
        assert _reaction_position(SESSIONS, EarningsEvent(date(2026, 10, 16), "amc")) is None


class TestGetEarningsWindow:
    def test_covers_five_sessions_before_to_ten_after_reaction(self, collector):
        window, metrics = collector.get_earnings_window("AAPL", EarningsEvent(date(2026, 7, 30), "amc"), "XLK")

        assert window["day_offset"].tolist() == list(range(-5, 11))
        assert window.index[5].date() == date(2026, 7, 31)
        assert metrics["reaction_date"] == "2026-07-31"
        assert metrics["is_partial"] is False

    def test_includes_moving_averages_from_full_history(self, collector, fetcher):
        bars = _daily_bars(100.0, step=1.0)
        fetcher.get_stock_data.side_effect = lambda symbol, **kwargs: bars.copy()

        window, _ = collector.get_earnings_window("AAPL", EarningsEvent(date(2026, 7, 30), "amc"), "XLK")

        reaction_close = window.loc["2026-07-31", "close"]
        assert window.loc["2026-07-31", "sma_20"] == pytest.approx(reaction_close - 9.5)
        assert window.loc["2026-07-31", "sma_200"] == pytest.approx(reaction_close - 99.5)

    def test_includes_sector_and_market_closes(self, collector):
        window, _ = collector.get_earnings_window("AAPL", EarningsEvent(date(2026, 7, 30), "amc"), "XLK")

        assert {"XLK_close", "SPY_close"} <= set(window.columns)

    def test_computes_reaction_metrics_against_pre_earnings_close(self, collector, fetcher):
        bars = _daily_bars(100.0)
        bars.loc["2026-07-31", ["open", "close", "volume"]] = [110.0, 105.0, 3000]
        fetcher.get_stock_data.side_effect = lambda symbol, **kwargs: (
            bars.copy() if symbol == "AAPL" else _daily_bars(50.0)
        )

        _, metrics = collector.get_earnings_window("AAPL", EarningsEvent(date(2026, 7, 30), "amc"), "XLK")

        assert metrics["gap_pct"] == 10.0
        assert metrics["stock_day0_return_pct"] == 5.0
        assert metrics["day0_volume_ratio"] == 3.0
        assert metrics["abnormal_day0_vs_sector_pct"] == 5.0

    def test_flags_partial_window_for_recent_release(self, collector):
        window, metrics = collector.get_earnings_window("AAPL", EarningsEvent(date(2026, 10, 13), "bmo"), "XLK")

        assert window["day_offset"].max() == 3
        assert metrics["is_partial"] is True
        assert metrics["stock_t5_return_pct"] is None


class TestGetIntradayWindow:
    def test_requests_extended_hours_from_two_sessions_before_to_two_after(self, collector, fetcher):
        collector.get_intraday_window("AAPL", EarningsEvent(date(2026, 7, 30), "amc"))

        fetcher.get_intraday_bars.assert_called_once_with(
            "AAPL", datetime(2026, 7, 29, 4, 0), datetime(2026, 8, 4, 20, 0), 5
        )

    def test_returns_empty_frame_when_no_intraday_data(self, collector, fetcher):
        fetcher.get_intraday_bars.return_value = None

        assert collector.get_intraday_window("AAPL", EarningsEvent(date(2026, 7, 30), "amc")).empty


class TestGetSectorPerformance:
    def test_compares_stock_to_sector_and_market_over_63_sessions(self, collector, fetcher):
        bars = {"AAPL": _daily_bars(100.0, step=0.1), "XLK": _daily_bars(50.0), "SPY": _daily_bars(500.0)}
        fetcher.get_stock_data.side_effect = lambda symbol, **kwargs: bars[symbol].copy()

        closes, summary = collector.get_sector_performance("AAPL", "XLK")

        assert len(closes) == 64
        assert summary["trading_days"] == 63
        assert summary["return_pct"]["XLK"] == 0.0
        assert summary["stock_vs_sector_pct"] == summary["return_pct"]["AAPL"] > 0

    def test_skips_sector_comparison_without_sector_etf(self, collector):
        closes, summary = collector.get_sector_performance("AAPL", None)

        assert list(closes.columns) == ["AAPL", "SPY"]
        assert summary["stock_vs_sector_pct"] is None


def _eps_trend():
    return pd.DataFrame(
        {"current": [1.2, 4.0], "7daysAgo": [1.1, 3.9], "30daysAgo": [1.1, 3.8],
         "60daysAgo": [1.0, 3.5], "90daysAgo": [0.9, 3.4]},
        index=pd.Index(["0q", "0y"], name="period"),
    )


class TestGetForecastRevision:
    def test_compares_last_snapshot_before_release_to_current(self, fetcher, tmp_path):
        fetcher.get_eps_trend.return_value = _eps_trend()
        collector = EarningsPriceContextCollector(fetcher=fetcher, output_dir=str(tmp_path), as_of=date.today())

        revision = collector.get_forecast_revision("AAPL", EarningsEvent(date.today() - timedelta(days=45), "amc"))

        next_quarter = revision["periods"][0]
        assert (next_quarter["label"], next_quarter["before"], next_quarter["after"]) == ("next quarter", 1.0, 1.1)
        assert next_quarter["change_pct"] == pytest.approx(20.0)
        assert revision["before_snapshot"] == (date.today() - timedelta(days=60)).isoformat()

    def test_unavailable_for_release_older_than_trend_history(self, fetcher, tmp_path):
        collector = EarningsPriceContextCollector(fetcher=fetcher, output_dir=str(tmp_path), as_of=date.today())

        revision = collector.get_forecast_revision("AAPL", EarningsEvent(date.today() - timedelta(days=95), "amc"))

        assert revision["available"] is False
        fetcher.get_eps_trend.assert_not_called()

    def test_unavailable_for_past_as_of_collection(self, collector):
        revision = collector.get_forecast_revision("AAPL", EarningsEvent(date(2026, 9, 1), "amc"))

        assert revision["available"] is False


class TestCollect:
    def test_writes_manifest_and_csv_files(self, collector, tmp_path):
        collector.collect("aapl")

        out_dir = tmp_path / "AAPL" / AS_OF.isoformat()
        assert (out_dir / "daily_90d.csv").exists()
        assert (out_dir / "sector_performance_63d.csv").exists()
        assert (out_dir / "earnings" / "2026-07-30" / "daily_window.csv").exists()
        assert (out_dir / "earnings" / "2026-07-30" / "intraday_5min.csv").exists()
        manifest = json.loads((out_dir / "manifest.json").read_text())
        assert manifest["sector_etf"] == "XLK"
        assert manifest["upcoming_earnings"]["release_date"] == "2026-11-02"
        assert len(manifest["earnings"]) == 2

    def test_records_missing_intraday_file_as_none(self, collector, fetcher):
        fetcher.get_intraday_bars.return_value = None

        manifest = collector.collect("AAPL")

        assert manifest["earnings"][0]["files"]["intraday_5min"] is None
        assert manifest["earnings"][0]["intraday_bars"] == 0

    def test_unmapped_sector_has_no_sector_etf(self, collector, fetcher):
        fetcher.get_company_info.return_value = {"sector": ""}

        manifest = collector.collect("AAPL")

        assert manifest["sector_etf"] is None
        assert manifest["sector_performance"]["stock_vs_sector_pct"] is None
