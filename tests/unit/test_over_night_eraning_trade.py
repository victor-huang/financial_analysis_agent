"""Unit tests for the overnight earnings trade backtest."""
import json
from datetime import date

import pandas as pd
import pytest

from over_night_eraning_trade import (
    collect_contexts,
    collect_follow_through,
    collect_trades,
    earnings_results,
    exit_labels,
    filter_trades,
    find_context_dir,
    forecast_revision_table,
    gap_follow_through,
    reaction_day_profile,
    latest_release_levels,
    main,
    release_levels,
    simulate_trade,
    summarize,
    summarize_by_technical_score,
    summarize_follow_through,
    technical_setup,
    to_short,
)

RELEASE = "2026-09-01"


def _write_event_files(event_dir, intraday_rows, auction_open=110.0, with_sma=True):
    event_dir.mkdir(parents=True)
    daily = pd.DataFrame(
        {"date": ["2026-09-01", "2026-09-02"], "day_offset": [-1, 0],
         "open": [99.0, auction_open], "close": [100.0, 105.0], "volume": [1000, 1000],
         "high": [101.0, 112.0], "low": [98.0, 94.0]}
    )
    if with_sma:
        daily["sma_20"] = [125.0, 124.0]
        daily["sma_50"] = [90.0, 91.0]
        daily["sma_200"] = [None, None]
    daily.to_csv(event_dir / "daily_window.csv", index=False)
    intraday = pd.DataFrame(intraday_rows, columns=["timestamp", "open", "close"])
    intraday["high"], intraday["low"] = intraday[["open", "close"]].max(axis=1), intraday[["open", "close"]].min(axis=1)
    intraday.assign(volume=100).to_csv(
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

        assert trade["exit_prices"] == {
            "open (auction)": 110.0, "open": 108.0, "+5m": 105.0, "+10m": 95.0, "day-0 close": 105.0,
        }
        assert trade["returns_pct"]["+5m"] == pytest.approx(5.0)
        assert trade["returns_pct"]["+10m"] == pytest.approx(-5.0)

    def test_exit_uses_last_trade_when_interval_has_no_new_bar(self, context_dir):
        trade, _ = simulate_trade(_event(), context_dir, 15, 15, 5)

        assert trade["exit_prices"]["+15m"] == 95.0
        assert trade["returns_pct"]["+15m"] == pytest.approx(-5.0)

    def test_peak_and_low_cover_bars_from_open_to_each_sell_time(self, context_dir):
        trade, _ = simulate_trade(_event(), context_dir, 15, 10, 5)

        assert trade["peaks_pct"]["+5m"] == pytest.approx(8.0)
        assert trade["lows_pct"]["+5m"] == pytest.approx(5.0)
        assert trade["peaks_pct"]["+10m"] == pytest.approx(8.0)
        assert trade["lows_pct"]["+10m"] == pytest.approx(-5.0)

    def test_day0_peak_and_low_use_full_session_high_and_low(self, context_dir):
        trade, _ = simulate_trade(_event(), context_dir, 15, 10, 5)

        assert trade["peaks_pct"]["day-0 close"] == pytest.approx(12.0)
        assert trade["lows_pct"]["day-0 close"] == pytest.approx(-6.0)

    def test_entry_staleness_is_zero_when_bar_ending_at_entry_traded(self, context_dir):
        trade, _ = simulate_trade(_event(), context_dir, 15, 10, 5)

        assert trade["entry_staleness_min"] == 0.0

    def test_entry_staleness_measures_minutes_since_last_trade(self, tmp_path):
        path = tmp_path / "MDB" / "2026-10-18"
        _write_event_files(path / "earnings" / RELEASE, [r for r in INTRADAY if r[0][11:] not in ("19:40", "19:55")])

        trade, _ = simulate_trade(_event(), path, 15, 10, 5)

        assert trade["entry_price"] == 90.0
        assert trade["entry_staleness_min"] == pytest.approx(215.0)

    def test_skips_trade_with_stale_entry_when_limit_set(self, tmp_path):
        path = tmp_path / "MDB" / "2026-10-18"
        _write_event_files(path / "earnings" / RELEASE, [r for r in INTRADAY if r[0][11:] not in ("19:40", "19:55")])

        trade, reason = simulate_trade(_event(), path, 15, 10, 5, max_entry_staleness=30)

        assert trade is None
        assert "215 min" in reason

    def test_skips_when_intraday_and_daily_prices_are_on_different_scales(self, tmp_path):
        path = tmp_path / "OPAD" / "2026-10-18"
        scaled = [(t, o * 10, c * 10) if t.startswith(RELEASE) else (t, o, c) for t, o, c in INTRADAY]
        _write_event_files(path / "earnings" / RELEASE, scaled)

        trade, reason = simulate_trade(_event(), path, 15, 10, 5)

        assert trade is None
        assert "price scales differ" in reason

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


def _technical_window(close=100.0, sma_20=95.0, sma_50=90.0, sma_200=90.0, high_52w=130.0, close_5d_ago=97.0):
    rows = [{"day_offset": o, "close": close_5d_ago if o == -5 else close, "volume": 1000,
             "sma_20": sma_20, "sma_50": sma_50, "sma_200": sma_200, "high_52w": high_52w} for o in range(-5, 1)]
    return pd.DataFrame(rows).set_index("day_offset")


class TestTechnicalSetup:
    def test_scores_all_conditions_met(self):
        setup = technical_setup(_technical_window(), after_hours_volume=500, entry_price=110.0)

        assert setup["close_vs_sma20_pct"] == pytest.approx((100 / 95 - 1) * 100)
        assert setup["run_up_5d_pct"] == pytest.approx((100 / 97 - 1) * 100)
        assert setup["room_to_resistance_pct"] == pytest.approx((130 / 110 - 1) * 100)
        assert setup["ah_vol_vs_adv"] == pytest.approx(0.5)
        assert setup["technical_score"] == 5

    def test_nearest_level_above_entry_is_the_resistance(self):
        setup = technical_setup(_technical_window(sma_50=115.0), after_hours_volume=500, entry_price=110.0)

        assert setup["room_to_resistance_pct"] == pytest.approx((115 / 110 - 1) * 100)
        assert setup["technical_score"] == 4

    def test_no_resistance_above_entry_counts_as_room(self):
        setup = technical_setup(_technical_window(high_52w=105.0), after_hours_volume=500, entry_price=110.0)

        assert setup["room_to_resistance_pct"] is None
        assert setup["technical_score"] == 5

    def test_extended_above_sma200_and_light_after_hours_volume_lose_points(self):
        setup = technical_setup(_technical_window(sma_200=70.0), after_hours_volume=100, entry_price=110.0)

        assert setup["close_vs_sma200_pct"] == pytest.approx((100 / 70 - 1) * 100)
        assert setup["technical_score"] == 3

    def test_measures_distance_below_52_week_high(self):
        setup = technical_setup(_technical_window(high_52w=125.0), after_hours_volume=500, entry_price=110.0)

        assert setup["pct_below_52w_high"] == pytest.approx(20.0)

    def test_score_is_none_without_moving_averages(self):
        window = _technical_window().drop(columns=["sma_20", "sma_50", "sma_200"])

        assert technical_setup(window, after_hours_volume=500, entry_price=110.0)["technical_score"] is None


class TestFilterTrades:
    def _trades(self):
        return pd.DataFrame({
            "ticker": ["A", "B", "C", "D"],
            "pct_below_52w_high": [2.0, 3.0, 12.0, None],
            "eps_surprise_pct": [-10.0, 5.0, -20.0, -15.0],
            "revenue_surprise_pct": [-3.0, -4.0, -5.0, -6.0],
        })

    def test_keeps_releases_near_52_week_high_with_big_misses(self):
        kept = filter_trades(self._trades(), max_pct_below_52w_high=5, max_eps_surprise=-5, max_revenue_surprise=-2)

        assert kept["ticker"].tolist() == ["A"]

    def test_drops_trades_missing_a_filtered_value(self):
        kept = filter_trades(self._trades(), max_pct_below_52w_high=50)

        assert kept["ticker"].tolist() == ["A", "B", "C"]

    def test_keeps_after_hours_moves_within_bounds(self):
        trades = self._trades().assign(after_hours_move_pct=[-6.0, 0.0, 2.0, 8.0])

        assert filter_trades(trades, min_after_hours_move=0)["ticker"].tolist() == ["C", "D"]
        assert filter_trades(trades, max_after_hours_move=-5)["ticker"].tolist() == ["A"]

    def test_min_pct_below_52_week_high_excludes_stocks_near_the_high(self):
        kept = filter_trades(self._trades(), min_pct_below_52w_high=5)

        assert kept["ticker"].tolist() == ["C"]

    def test_keeps_everything_without_filters(self):
        assert len(filter_trades(self._trades())) == 4


class TestToShort:
    def test_negates_returns_and_swaps_peak_and_low(self):
        trades = pd.DataFrame({"+5m": [-4.0], "peak +5m": [1.0], "low +5m": [-6.0]})

        short = to_short(trades, ["+5m"])

        assert short.loc[0, "+5m"] == 4.0
        assert short.loc[0, "peak +5m"] == 6.0
        assert short.loc[0, "low +5m"] == -1.0


class TestSummarizeByTechnicalScore:
    def test_groups_returns_by_score_bucket(self):
        trades = pd.DataFrame({
            "technical_score": [1, 2, 3, 5],
            "open (auction)": [-1.0, 1.0, 2.0, 4.0],
            "+40m": [-2.0, 0.0, 3.0, 6.0],
            "day-0 close": [-3.0, 1.0, 4.0, 8.0],
        })

        summary = summarize_by_technical_score(trades, ["open (auction)", "+40m", "day-0 close"])

        assert summary.loc["0-2", "trades"] == 2
        assert summary.loc["0-2", "win_pct (open (auction))"] == 50.0
        assert summary.loc["4-5", "avg_pct (+40m)"] == 6.0
        assert summary.loc["3", "median_pct (day-0 close)"] == 4.0


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

    def test_includes_52_week_high_and_low_when_collected(self, tmp_path):
        path = tmp_path / "MDB" / "2026-10-18"
        _write_event_files(path / "earnings" / RELEASE, INTRADAY)
        daily_path = path / "earnings" / RELEASE / "daily_window.csv"
        daily = pd.read_csv(daily_path)
        daily["high_52w"], daily["low_52w"] = 150.0, 60.0
        daily.to_csv(daily_path, index=False)

        levels, _ = release_levels(_event(), path)

        assert levels.loc["52-week high", "vs_extended_close_pct"] == pytest.approx(25.0)
        assert levels.loc["52-week low", "role"].startswith("support")

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


def _write_gap_event(context_dir, release, prior_close, day_open, session_bars, timing="amc"):
    """Write a release whose reaction session (offset 0) is the day after `release`."""
    event_dir = context_dir / "earnings" / release
    event_dir.mkdir(parents=True)
    reaction_day = pd.Timestamp(release) + pd.offsets.BDay(1)
    dates = [pd.Timestamp(release) - pd.offsets.BDay(n) for n in (4, 3, 2, 1)] + [pd.Timestamp(release)]
    dates += [reaction_day + pd.offsets.BDay(n) for n in range(0, 6)]
    rows = []
    for offset, day in zip(range(-5, 6), dates):
        close = prior_close if offset < 0 else (day_open * 1.05 if offset == 0 else day_open * 1.1)
        rows.append({"date": day.date(), "day_offset": offset, "open": day_open if offset == 0 else close,
                     "high": close * 1.01 if offset else day_open * 1.10, "low": close * 0.99 if offset else day_open * 0.98,
                     "close": close, "volume": 1000, "high_52w": 120.0, "low_52w": 50.0})
    pd.DataFrame(rows).to_csv(event_dir / "daily_window.csv", index=False)
    day = reaction_day.date().isoformat()
    pd.DataFrame(
        [(f"{day} {t}", o, h, l, c, v, vw) for t, o, h, l, c, v, vw in session_bars],
        columns=["timestamp", "open", "high", "low", "close", "volume", "vwap"],
    ).to_csv(event_dir / "intraday_5min.csv", index=False)
    return {"release_date": release, "timing": timing,
            "files": {"daily_window": f"earnings/{release}/daily_window.csv",
                      "intraday_5min": f"earnings/{release}/intraday_5min.csv"}}


GAP_SESSION = [
    ("09:30", 110.0, 112.0, 109.0, 111.0, 300, 110.5),
    ("09:35", 111.0, 111.5, 110.0, 111.0, 100, 111.0),
    ("09:40", 111.0, 113.0, 110.5, 112.5, 200, 112.0),
    ("09:55", 112.5, 113.0, 112.0, 112.8, 100, 112.5),
    ("10:00", 112.8, 114.0, 112.5, 113.0, 100, 113.0),
    ("15:55", 115.0, 116.0, 115.0, 115.5, 100, 115.5),
]
FLAT_SESSION = [("09:30", 100.0, 100.5, 99.5, 100.0, 200, 100.0), ("10:00", 100.0, 100.2, 99.8, 100.0, 50, 100.0)]


@pytest.fixture
def gap_context(tmp_path):
    path = tmp_path / "PL" / "2026-10-18"
    path.mkdir(parents=True)
    events = [
        _write_gap_event(path, "2026-09-03", prior_close=100.0, day_open=110.0, session_bars=GAP_SESSION),
        _write_gap_event(path, "2026-06-04", prior_close=100.0, day_open=100.0, session_bars=FLAT_SESSION),
    ]
    (path / "manifest.json").write_text(json.dumps({"earnings": events}))
    return path, events


class TestGapFollowThrough:
    def _result(self, gap_context, prior=True):
        path, events = gap_context
        profiles = [reaction_day_profile(e, path, 30) for e in events]
        return gap_follow_through(profiles[0], profiles[1:] if prior else [], 10, 30)

    def test_measures_gap_against_prior_close_and_normal_range(self, gap_context):
        result = self._result(gap_context)

        assert result["gap_pct"] == pytest.approx(10.0)
        assert result["gap_x_avg_range"] == pytest.approx(5.0)

    def test_detects_first_break_of_opening_range(self, gap_context):
        result = self._result(gap_context)

        assert result["or_width_pct"] == pytest.approx((112.0 / 109.0 - 1) * 100)
        assert result["or_break"] == "up"

    def test_compares_early_and_day_volume_to_prior_earnings_days(self, gap_context):
        result = self._result(gap_context)

        assert result["early_vol_vs_prior_earnings"] == pytest.approx(700 / 200)
        assert result["day_vol_vs_prior_earnings"] == pytest.approx(1.0)

    def test_volume_ratios_empty_without_prior_earnings(self, gap_context):
        result = self._result(gap_context, prior=False)

        assert result["early_vol_vs_prior_earnings"] is None

    def test_measures_price_against_vwap_at_check_time(self, gap_context):
        result = self._result(gap_context)

        vwap = (110.5 * 300 + 111.0 * 100 + 112.0 * 200 + 112.5 * 100) / 700
        assert result["vs_vwap_at_check_pct"] == pytest.approx((112.8 / vwap - 1) * 100)

    def test_measures_distance_to_52_week_high_and_low_from_open(self, gap_context):
        result = self._result(gap_context)

        assert result["to_52w_high_pct"] == pytest.approx((120.0 / 110.0 - 1) * 100)
        assert result["above_52w_low_pct"] == pytest.approx((110.0 / 50.0 - 1) * 100)

    def test_reports_day0_outcomes_from_open_and_next_days_from_close(self, gap_context):
        result = self._result(gap_context)

        assert result["close_from_open_pct"] == pytest.approx(5.0)
        assert result["high_from_open_pct"] == pytest.approx(10.0)
        assert result["or_end_to_close_pct"] == pytest.approx((115.5 / 111.0 - 1) * 100)
        assert result["check_to_close_pct"] == pytest.approx((115.5 / 112.8 - 1) * 100)
        assert result["t1_pct"] == pytest.approx((1.1 / 1.05 - 1) * 100)


    def test_returns_none_without_trades_in_opening_range(self, tmp_path):
        path = tmp_path / "PL" / "2026-10-18"
        event = _write_gap_event(path, "2026-09-03", 100.0, 110.0, [r for r in GAP_SESSION if r[0] >= "09:55"])

        assert gap_follow_through(reaction_day_profile(event, path, 30), [], 10, 30) is None


    def test_profile_is_none_when_prices_are_on_different_scales(self, tmp_path):
        path = tmp_path / "PL" / "2026-10-18"
        scaled = [(t, o * 10, h * 10, l * 10, c * 10, v, vw * 10) for t, o, h, l, c, v, vw in GAP_SESSION]
        event = _write_gap_event(path, "2026-09-03", 100.0, 110.0, scaled)

        assert reaction_day_profile(event, path, 30) is None


class TestCollectFollowThrough:
    def test_includes_only_releases_gapping_up_at_least_min_gap(self, gap_context):
        path, _ = gap_context

        follow = collect_follow_through(["PL"], path.parent.parent, None, 2.0, 10, 30)

        assert follow["release_date"].tolist() == ["2026-09-03"]

    def test_includes_before_open_releases(self, tmp_path):
        path = tmp_path / "PL" / "2026-10-18"
        path.mkdir(parents=True)
        event = _write_gap_event(path, "2026-09-03", 100.0, 110.0, GAP_SESSION, timing="bmo")
        (path / "manifest.json").write_text(json.dumps({"earnings": [event]}))

        follow = collect_follow_through(["PL"], tmp_path, None, 2.0, 10, 30)

        assert follow["timing"].tolist() == ["bmo"]


    def test_excludes_releases_with_unknown_timing(self, tmp_path):
        path = tmp_path / "PL" / "2026-10-18"
        path.mkdir(parents=True)
        event = _write_gap_event(path, "2026-09-03", 100.0, 110.0, GAP_SESSION, timing="unknown")
        (path / "manifest.json").write_text(json.dumps({"earnings": [event]}))

        assert collect_follow_through(["PL"], tmp_path, None, 2.0, 10, 30).empty


class TestMain:
    def test_rejects_entry_minutes_not_aligned_to_5_min_bars(self, mocker):
        mocker.patch("sys.argv", ["over_night_eraning_trade.py", "MDB", "--entry-minutes-before-close", "12"])

        with pytest.raises(SystemExit):
            main()


class TestSummarizeFollowThrough:
    def test_groups_outcomes_by_signal(self):
        follow = pd.DataFrame({
            "gap_pct": [5.0, 20.0], "or_break": ["down", "up"], "early_vol_vs_prior_earnings": [0.5, 2.0],
            "vs_vwap_at_check_pct": [-1.0, 1.0], "to_52w_high_pct": [10.0, -2.0],
            "close_from_open_pct": [-4.0, 6.0], "or_end_to_close_pct": [-3.0, 4.0], "check_to_close_pct": [-2.0, 3.0],
            "high_from_open_pct": [1.0, 9.0], "low_from_open_pct": [-6.0, -2.0], "t1_pct": [-1.0, 3.0],
        })

        summary = summarize_follow_through(follow, 30)

        assert summary.loc["all gap-ups", "releases"] == 2
        assert summary.loc["opening range broke up", "avg_close_from_open_pct"] == 6.0
        assert summary.loc["gap <=8%", "close_above_open_pct"] == 0.0
        assert summary.loc["opened above 52-week high", "avg_t1_pct"] == 3.0
        assert "opening range broke none" not in summary.index


class TestCollectContexts:
    def test_collects_every_ticker(self, mocker, tmp_path):
        collector = mocker.patch("over_night_eraning_trade.EarningsPriceContextCollector").return_value

        collect_contexts(["MDB", "PL"], tmp_path, None, 4, 2, resume=False)

        assert sorted(c.args[0] for c in collector.collect.call_args_list) == ["MDB", "PL"]

    def test_resume_skips_tickers_already_collected_for_as_of(self, mocker, tmp_path):
        collector = mocker.patch("over_night_eraning_trade.EarningsPriceContextCollector").return_value
        collector.as_of = date(2026, 10, 18)
        (tmp_path / "MDB" / "2026-10-18").mkdir(parents=True)
        (tmp_path / "MDB" / "2026-10-18" / "manifest.json").write_text("{}")

        collect_contexts(["MDB", "PL"], tmp_path, date(2026, 10, 18), 4, 1, resume=True)

        assert [c.args[0] for c in collector.collect.call_args_list] == ["PL"]

    def test_reports_failed_tickers_without_stopping(self, mocker, tmp_path):
        def collect(ticker, quarters):
            if ticker == "BAD":
                raise ValueError("boom")
            return {}

        collector = mocker.patch("over_night_eraning_trade.EarningsPriceContextCollector").return_value
        collector.collect.side_effect = collect

        failures = collect_contexts(["BAD", "PL"], tmp_path, None, 4, 1, resume=False)

        assert failures == [("BAD", "boom")]
        assert collector.collect.call_count == 2


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
    def test_reports_average_peak_and_low_per_exit(self):
        trades = pd.DataFrame({"+5m": [1.0, -1.0], "peak +5m": [3.0, 1.0], "low +5m": [-1.0, -3.0]})

        summary = summarize(trades, ["+5m"])

        assert summary.loc["+5m", "avg_peak_pct"] == 2.0
        assert summary.loc["+5m", "avg_low_pct"] == -2.0

    def test_computes_win_rate_and_average_per_exit(self):
        trades = pd.DataFrame({"open": [2.0, -1.0, 3.0, None]})

        summary = summarize(trades, ["open"])

        assert summary.loc["open", "trades"] == 3
        assert summary.loc["open", "win_rate_pct"] == pytest.approx(66.6667, rel=1e-4)
        assert summary.loc["open", "avg_return_pct"] == pytest.approx(4 / 3)


class TestExitLabels:
    def test_lists_open_exits_then_each_interval(self):
        assert exit_labels(15, 5) == ["open (auction)", "open", "+5m", "+10m", "+15m", "day-0 close"]
