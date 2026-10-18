"""Unit tests for the overnight earnings trade backtest."""
import json

import pandas as pd
import pytest

from over_night_eraning_trade import (
    collect_trades,
    earnings_results,
    exit_labels,
    find_context_dir,
    forecast_revision_table,
    latest_release_levels,
    release_levels,
    simulate_trade,
    summarize,
)

RELEASE = "2026-09-01"


def _write_event_files(event_dir, intraday_rows, auction_open=110.0, with_sma=True):
    event_dir.mkdir(parents=True)
    daily = pd.DataFrame(
        {"date": ["2026-09-01", "2026-09-02"], "day_offset": [-1, 0],
         "open": [99.0, auction_open], "close": [100.0, 105.0]}
    )
    if with_sma:
        daily["sma_20"] = [125.0, 124.0]
        daily["sma_50"] = [90.0, 91.0]
        daily["sma_200"] = [None, None]
    daily.to_csv(event_dir / "daily_window.csv", index=False)
    pd.DataFrame(intraday_rows, columns=["timestamp", "open", "close"]).to_csv(
        event_dir / "intraday_5min.csv", index=False
    )


def _event(timing="amc"):
    return {
        "release_date": RELEASE,
        "timing": timing,
        "eps_estimate": 1.0,
        "eps_actual": 1.2,
        "revenue_estimate": 200_000_000.0,
        "revenue_actual": 190_000_000.0,
        "files": {
            "daily_window": f"earnings/{RELEASE}/daily_window.csv",
            "intraday_5min": f"earnings/{RELEASE}/intraday_5min.csv",
        },
    }


INTRADAY = [
    ("2026-09-01 15:55", 100.0, 100.0),
    ("2026-09-01 16:05", 100.0, 90.0),
    ("2026-09-01 19:40", 91.0, 100.0),
    ("2026-09-01 19:55", 101.0, 120.0),
    ("2026-09-02 09:25", 104.0, 104.0),
    ("2026-09-02 09:30", 108.0, 105.0),
    ("2026-09-02 09:35", 105.0, 95.0),
]


@pytest.fixture
def context_dir(tmp_path):
    path = tmp_path / "MDB" / "2026-10-18"
    _write_event_files(path / "earnings" / RELEASE, INTRADAY)
    (path / "manifest.json").write_text(json.dumps({"earnings": [_event()]}))
    return path


class TestSimulateTrade:
    def test_buys_at_last_after_hours_trade_before_entry_time(self, context_dir):
        trade, _ = simulate_trade(_event(), context_dir, 15, 10, 5)

        assert trade["entry_price"] == 100.0
        assert trade["entry_time"] == "2026-09-01 19:45"

    def test_sells_at_auction_open_first_trade_and_each_interval(self, context_dir):
        trade, _ = simulate_trade(_event(), context_dir, 15, 10, 5)

        assert trade["exit_prices"] == {"open (auction)": 110.0, "open": 108.0, "+5m": 105.0, "+10m": 95.0}
        assert trade["returns_pct"]["+5m"] == pytest.approx(5.0)
        assert trade["returns_pct"]["+10m"] == pytest.approx(-5.0)

    def test_exit_uses_last_trade_when_interval_has_no_new_bar(self, context_dir):
        trade, _ = simulate_trade(_event(), context_dir, 15, 15, 5)

        assert trade["exit_prices"]["+15m"] == 95.0
        assert trade["returns_pct"]["+15m"] == pytest.approx(-5.0)

    def test_after_hours_move_compares_entry_to_regular_close(self, context_dir):
        trade, _ = simulate_trade(_event(), context_dir, 15, 10, 5)

        assert trade["earnings"]["after_hours_move_pct"] == pytest.approx(0.0)

    def test_skips_before_open_releases(self, context_dir):
        trade, reason = simulate_trade(_event(timing="bmo"), context_dir, 15, 10, 5)

        assert trade is None
        assert "not after close" in reason

    def test_skips_when_no_after_hours_trades_before_entry(self, tmp_path):
        path = tmp_path / "MDB" / "2026-10-18"
        _write_event_files(path / "earnings" / RELEASE, [r for r in INTRADAY if not "16:00" < r[0][11:] < "20:00"])

        trade, reason = simulate_trade(_event(), path, 15, 10, 5)

        assert trade is None
        assert "no after-hours trades" in reason

    def test_skips_when_intraday_file_missing(self, context_dir):
        event = {**_event(), "files": {"daily_window": "x.csv", "intraday_5min": None}}

        trade, reason = simulate_trade(event, context_dir, 15, 10, 5)

        assert trade is None
        assert "missing" in reason


class TestEarningsResults:
    def test_reports_eps_beat_as_positive_surprise(self):
        results = earnings_results(_event())

        assert results["eps_surprise_pct"] == pytest.approx(20.0)

    def test_reports_revenue_miss_in_millions_as_negative_surprise(self):
        results = earnings_results(_event())

        assert (results["revenue_estimate_m"], results["revenue_actual_m"]) == (200.0, 190.0)
        assert results["revenue_surprise_pct"] == pytest.approx(-5.0)

    def test_smaller_loss_than_expected_is_a_beat(self):
        results = earnings_results({**_event(), "eps_estimate": -0.2, "eps_actual": -0.1})

        assert results["eps_surprise_pct"] == pytest.approx(50.0)

    def test_missing_revenue_leaves_surprise_empty(self):
        results = earnings_results({**_event(), "revenue_estimate": None, "revenue_actual": None})

        assert results["revenue_surprise_pct"] is None
        assert results["revenue_actual_m"] is None


class TestForecastRevisionTable:
    def test_labels_snapshot_columns_with_dates(self):
        manifest = {"forecast_revision": {
            "available": True, "source": "yfinance eps_trend",
            "before_snapshot": "2026-08-19", "after_snapshot": "2026-09-18",
            "periods": [{"period": "0q", "label": "next quarter", "before": 0.73, "after": 1.06,
                         "current": 1.13, "change_pct": 55.2}],
        }}

        table, _ = forecast_revision_table(manifest)

        assert table.loc["next quarter", "before (2026-08-19)"] == 0.73
        assert table.loc["next quarter", "change_pct (before -> current)"] == 55.2

    def test_returns_reason_when_unavailable(self):
        table, reason = forecast_revision_table({"forecast_revision": {"available": False, "reason": "too old"}})

        assert table is None
        assert reason == "too old"

    def test_asks_to_recollect_for_older_collections(self):
        table, reason = forecast_revision_table({})

        assert table is None
        assert "--collect" in reason


class TestReleaseLevels:
    def test_uses_last_after_hours_trade_as_extended_close(self, context_dir):
        levels, _ = release_levels(_event(), context_dir)

        assert levels.loc["extended close", "price"] == 120.0
        assert levels.loc["regular close", "vs_extended_close_pct"] == pytest.approx(-16.6667, rel=1e-4)

    def test_moving_average_above_extended_close_is_resistance(self, context_dir):
        levels, _ = release_levels(_event(), context_dir)

        assert levels.loc["SMA 20", "vs_extended_close_pct"] == pytest.approx(4.1667, rel=1e-4)
        assert levels.loc["SMA 20", "role"].startswith("resistance")

    def test_moving_average_below_extended_close_is_support(self, context_dir):
        levels, _ = release_levels(_event(), context_dir)

        assert levels.loc["SMA 50", "vs_extended_close_pct"] == pytest.approx(-25.0)
        assert levels.loc["SMA 50", "role"].startswith("support")

    def test_omits_moving_average_without_enough_history(self, context_dir):
        levels, _ = release_levels(_event(), context_dir)

        assert "SMA 200" not in levels.index

    def test_asks_to_recollect_when_moving_averages_missing(self, tmp_path):
        path = tmp_path / "MDB" / "2026-10-18"
        _write_event_files(path / "earnings" / RELEASE, INTRADAY, with_sma=False)

        levels, reason = release_levels(_event(), path)

        assert levels is None
        assert "--collect" in reason

    def test_latest_release_levels_uses_most_recent_release(self, context_dir):
        results = latest_release_levels(["MDB"], context_dir.parent.parent, None)

        ticker, event, levels, _ = results[0]
        assert (ticker, event["release_date"]) == ("MDB", RELEASE)
        assert levels is not None


class TestFindContextDir:
    def test_returns_latest_collection(self, tmp_path):
        for as_of in ("2026-09-01", "2026-10-18"):
            (tmp_path / "MDB" / as_of).mkdir(parents=True)
            (tmp_path / "MDB" / as_of / "manifest.json").write_text("{}")

        assert find_context_dir(tmp_path, "mdb").name == "2026-10-18"

    def test_returns_none_without_collected_data(self, tmp_path):
        assert find_context_dir(tmp_path, "MDB") is None


class TestCollectTrades:
    def test_returns_one_row_per_trade_with_return_columns(self, context_dir):
        trades, skipped = collect_trades(["MDB"], context_dir.parent.parent, None, 15, 10, 5)

        assert len(trades) == 1
        assert trades.iloc[0]["+5m"] == pytest.approx(5.0)
        assert skipped == []

    def test_reports_tickers_without_data_as_skipped(self, context_dir):
        _, skipped = collect_trades(["CRWD"], context_dir.parent.parent, None, 15, 10, 5)

        assert skipped[0][0] == "CRWD"


class TestSummarize:
    def test_computes_win_rate_and_average_per_exit(self):
        trades = pd.DataFrame({"open": [2.0, -1.0, 3.0, None]})

        summary = summarize(trades, ["open"])

        assert summary.loc["open", "trades"] == 3
        assert summary.loc["open", "win_rate_pct"] == pytest.approx(66.6667, rel=1e-4)
        assert summary.loc["open", "avg_return_pct"] == pytest.approx(4 / 3)


class TestExitLabels:
    def test_lists_open_exits_then_each_interval(self):
        assert exit_labels(15, 5) == ["open (auction)", "open", "+5m", "+10m", "+15m"]
