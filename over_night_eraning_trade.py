"""Backtest an overnight earnings trade from collected earnings price context.

Strategy, for each after-close (amc) earnings release:
- Buy N minutes before the after-hours session closes (default 19:45 ET) on the release day
- Sell the next morning at the market open, or at each 5-min mark up to M minutes after the open

Prices are the last trade before each time, taken from the collector's 5-min bars
(earnings/<release_date>/intraday_5min.csv). The "open" exit is the first regular-session
trade; "open (auction)" is the official opening price from the daily candle; "day-0 close" holds
until the reaction session's regular close.

--short runs the reverse trade: short at the entry and buy back at each exit, so returns are
the stock's fall; for a short, "peak" is the most favorable (lowest) price and "low" the worst
(highest). --max-pct-below-52w-high, --max-eps-surprise and --max-revenue-surprise keep only
releases near the 52-week high or missing estimates by at least the given %.

Each trade gets a technical score (0-5) from conditions known at entry: close above the 20-day SMA,
positive 5-day run-up, more than 10% room to the next resistance (20/50/200-day SMA or 52-week
high above the entry price), after-hours volume at least 0.3x the average daily volume, and close
less than 20% above the 200-day SMA. See docs/overnight_earnings_trade_findings.md.

Before-open (bmo) releases are skipped: the evening before, earnings are not reported yet.

For the latest release of each ticker it also reports the report day's extended-hours close
and its distance to the 20/50/200-day moving averages: a moving average above that price is
resistance (potential gain to reach it), one below is support (potential drawdown to reach it),
plus the 52-week high/low and how consensus EPS forecasts changed across that release
(when it is within 90 days).

Gap follow-through: for every release (amc or bmo) whose reaction session gapped up by at least
--min-gap %, it measures setup signals known early in the session (gap vs normal daily range,
opening-range breakout, early volume vs earlier earnings days, VWAP, 52-week high/low) and the
outcome (day-0 high/low/close from the open, T+1 and T+5), then summarizes outcomes by signal.

Usage:
    python over_night_eraning_trade.py MDB --collect
    python over_night_eraning_trade.py MDB CRWD SNOW --max-minutes 60 --interval 5 --output trades.csv
"""

import argparse
import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

from financial_analysis_agent.config import get_config
from financial_analysis_agent.financial.data_fetcher import FinancialDataFetcher
from financial_analysis_agent.financial.earnings_price_context import (
    EPS_SURPRISE_CAP_PCT,
    MOVING_AVERAGE_WINDOWS,
    REVENUE_SURPRISE_CAP_PCT,
    EarningsPriceContextCollector,
    surprise_pct,
)

logger = logging.getLogger(__name__)

AFTER_HOURS_START = time(16, 0)
AFTER_HOURS_END = time(20, 0)
MARKET_OPEN = time(9, 30)
BAR_MINUTES = 5
MAX_INTRADAY_DAILY_CLOSE_GAP_PCT = 15.0
AUCTION_OPEN_LABEL = "open (auction)"
FIRST_TRADE_OPEN_LABEL = "open"
DAY0_CLOSE_LABEL = "day-0 close"
PEAK_PREFIX = "peak "
LOW_PREFIX = "low "
MIN_ROOM_TO_RESISTANCE_PCT = 10.0
MIN_AFTER_HOURS_VOLUME_VS_ADV = 0.3
MAX_ABOVE_SMA200_PCT = 20.0
TECHNICAL_COLUMNS = [
    "close_vs_sma20_pct",
    "run_up_5d_pct",
    "room_to_resistance_pct",
    "ah_vol_vs_adv",
    "close_vs_sma200_pct",
    "pct_below_52w_high",
    "technical_score",
]
TECHNICAL_SCORE_BUCKETS = [("0-2", 0, 2), ("3", 3, 3), ("4-5", 4, 5)]
EARNINGS_COLUMNS = [
    "eps_estimate",
    "eps_actual",
    "eps_surprise_pct",
    "revenue_estimate_m",
    "revenue_actual_m",
    "revenue_surprise_pct",
    "eps_vs_usual_pts",
    "revenue_vs_usual_pts",
    "prior_beat_streak",
    "after_hours_move_pct",
    "ah_move_x_range",
]
FOLLOW_THROUGH_SETUP_COLUMNS = [
    "timing",
    "gap_pct",
    "gap_x_avg_range",
    "or_width_pct",
    "or_break",
    "early_vol_vs_prior_earnings",
    "vs_vwap_at_check_pct",
    "to_52w_high_pct",
    "above_52w_low_pct",
]
FOLLOW_THROUGH_OUTCOME_COLUMNS = [
    "day_vol_vs_prior_earnings",
    "high_from_open_pct",
    "low_from_open_pct",
    "close_from_open_pct",
    "or_end_to_close_pct",
    "check_to_close_pct",
    "t1_pct",
    "t5_pct",
]
GAP_BUCKETS = [(0, 8), (8, 15), (15, float("inf"))]


def default_data_dir() -> Path:
    return Path(get_config().get("paths.data")) / "earnings_price_context"


def exit_labels(max_minutes: int, interval: int) -> List[str]:
    return (
        [AUCTION_OPEN_LABEL, FIRST_TRADE_OPEN_LABEL]
        + [f"+{m}m" for m in range(interval, max_minutes + 1, interval)]
        + [DAY0_CLOSE_LABEL]
    )


def find_context_dir(data_dir: Path, ticker: str, as_of: Optional[date] = None) -> Optional[Path]:
    """Return the collected context directory for a ticker: the given as_of, else the latest one."""
    ticker_dir = data_dir / ticker.upper()
    if as_of:
        path = ticker_dir / as_of.isoformat()
        return path if (path / "manifest.json").exists() else None
    candidates = sorted(p for p in ticker_dir.glob("*") if (p / "manifest.json").exists())
    return candidates[-1] if candidates else None


def last_trade_before(bars: pd.DataFrame, moment: datetime, since: datetime) -> Optional[float]:
    """Close of the last 5-min bar that started in [since, moment), i.e. the last trade before `moment`."""
    window = bars[(bars.index >= since) & (bars.index < moment)]
    return float(window["close"].iloc[-1]) if not window.empty else None


def high_low_since_open(
    bars: pd.DataFrame, market_open: datetime, minutes: int
) -> Tuple[Optional[float], Optional[float]]:
    """Highest high and lowest low of the 5-min bars from the open up to `minutes` after it."""
    window = bars[(bars.index >= market_open) & (bars.index < market_open + timedelta(minutes=minutes))]
    if window.empty:
        return None, None
    return float(window["high"].max()), float(window["low"].min())


def path_labels(labels: List[str]) -> List[str]:
    """Exit labels that cover time after the open, for which a peak and a low exist."""
    return [label for label in labels if label not in (AUCTION_OPEN_LABEL, FIRST_TRADE_OPEN_LABEL)]


def price_scale_mismatch(bars: pd.DataFrame, day: date, daily_close: float) -> Optional[str]:
    """Reason string when the intraday bars and the daily candle disagree on the day's close.

    Compares the last regular-session 5-min close with the daily close; a large gap means the two
    sources are on different price scales (e.g. a reverse split adjusted in only one of them).
    """
    session = bars[
        (bars.index >= datetime.combine(day, MARKET_OPEN)) & (bars.index < datetime.combine(day, AFTER_HOURS_START))
    ]
    if session.empty or not daily_close:
        return None
    intraday_close = float(session["close"].iloc[-1])
    gap_pct = abs(intraday_close / daily_close - 1) * 100
    if gap_pct <= MAX_INTRADAY_DAILY_CLOSE_GAP_PCT:
        return None
    return (f"intraday close {intraday_close:g} vs daily close {daily_close:g} on {day} "
            "(price scales differ, likely a split adjusted in only one source)")


def minutes_since_last_bar(bars: pd.DataFrame, moment: datetime, since: datetime) -> Optional[float]:
    """Minutes from the end of the last 5-min bar that started in [since, moment) to `moment`.

    0 means the bar ending at `moment` traded; a large value means the last trade is stale.
    """
    window = bars[(bars.index >= since) & (bars.index < moment)]
    if window.empty:
        return None
    bar_end = window.index[-1] + timedelta(minutes=BAR_MINUTES)
    return max((moment - bar_end).total_seconds() / 60, 0.0)


def first_trade_at_or_after(bars: pd.DataFrame, moment: datetime, until: datetime) -> Optional[float]:
    window = bars[(bars.index >= moment) & (bars.index < until)]
    return float(window["open"].iloc[0]) if not window.empty else None


def simulate_trade(
    event: Dict,
    context_dir: Path,
    entry_minutes_before_close: int,
    max_minutes: int,
    interval: int,
    max_entry_staleness: Optional[float] = None,
) -> Tuple[Optional[Dict], Optional[str]]:
    """Simulate the overnight trade for one earnings release.

    Trades whose last after-hours trade before the entry is more than `max_entry_staleness`
    minutes old are skipped: that price was not available at the entry time.

    Returns:
        Tuple of (trade dict with entry and exit prices, None) or (None, skip reason)
    """
    if event.get("timing") != "amc":
        return None, f"release timing is {event.get('timing')!r}, not after close"

    files = event.get("files") or {}
    if not files.get("intraday_5min") or not files.get("daily_window"):
        return None, "missing intraday or daily window data"

    daily = pd.read_csv(context_dir / files["daily_window"], parse_dates=["date"], index_col="date")
    by_offset = daily.reset_index().set_index("day_offset")
    if -1 not in by_offset.index or 0 not in by_offset.index:
        return None, "reaction session not traded yet"
    entry_day = by_offset.at[-1, "date"].date()
    exit_day = by_offset.at[0, "date"].date()

    bars = pd.read_csv(context_dir / files["intraday_5min"], parse_dates=["timestamp"], index_col="timestamp")
    mismatch = price_scale_mismatch(bars, entry_day, float(by_offset.at[-1, "close"]))
    if mismatch:
        return None, mismatch

    entry_time = datetime.combine(entry_day, AFTER_HOURS_END) - timedelta(minutes=entry_minutes_before_close)
    after_hours_start = datetime.combine(entry_day, AFTER_HOURS_START)
    entry_price = last_trade_before(bars, entry_time, since=after_hours_start)
    if entry_price is None:
        return None, f"no after-hours trades on {entry_day} before {entry_time:%H:%M}"
    entry_staleness = minutes_since_last_bar(bars, entry_time, since=after_hours_start)
    if max_entry_staleness is not None and entry_staleness > max_entry_staleness:
        return None, f"last after-hours trade was {entry_staleness:.0f} min before the {entry_time:%H:%M} entry"

    market_open = datetime.combine(exit_day, MARKET_OPEN)
    exits = {
        AUCTION_OPEN_LABEL: float(by_offset.at[0, "open"]),
        FIRST_TRADE_OPEN_LABEL: first_trade_at_or_after(
            bars, market_open, until=market_open + timedelta(minutes=interval)
        ),
    }
    for minutes in range(interval, max_minutes + 1, interval):
        exits[f"+{minutes}m"] = last_trade_before(
            bars, market_open + timedelta(minutes=minutes), since=market_open
        )
    exits[DAY0_CLOSE_LABEL] = float(by_offset.at[0, "close"])

    highs_lows = {
        f"+{minutes}m": high_low_since_open(bars, market_open, minutes)
        for minutes in range(interval, max_minutes + 1, interval)
    }
    highs_lows[DAY0_CLOSE_LABEL] = (float(by_offset.at[0, "high"]), float(by_offset.at[0, "low"]))

    after_hours = bars[(bars.index >= datetime.combine(entry_day, AFTER_HOURS_START)) & (bars.index < entry_time)]
    trade = {
        "release_date": event["release_date"],
        "entry_time": entry_time.strftime("%Y-%m-%d %H:%M"),
        "entry_price": entry_price,
        "entry_staleness_min": entry_staleness,
        "regular_close": float(by_offset.at[-1, "close"]),
        "earnings": earnings_results(event),
        "technical": technical_setup(by_offset, after_hours["volume"].sum(), entry_price),
        "exit_prices": exits,
        "returns_pct": {
            label: _pct_from(entry_price, price) for label, price in exits.items()
        },
        "peaks_pct": {label: _pct_from(entry_price, high) for label, (high, _) in highs_lows.items()},
        "lows_pct": {label: _pct_from(entry_price, low) for label, (_, low) in highs_lows.items()},
    }
    trade["earnings"]["after_hours_move_pct"] = (entry_price / trade["regular_close"] - 1) * 100
    before = by_offset[by_offset.index < 0]
    avg_range_pct = ((before["high"] - before["low"]) / before["close"]).mean() * 100
    trade["earnings"]["ah_move_x_range"] = (
        trade["earnings"]["after_hours_move_pct"] / avg_range_pct if avg_range_pct else None
    )
    return trade, None


def _pct_from(base: float, price: Optional[float]) -> Optional[float]:
    return (price / base - 1) * 100 if price is not None else None


def technical_setup(by_offset: pd.DataFrame, after_hours_volume: float, entry_price: float) -> Dict:
    """Technical conditions known at entry, from the daily window (day -1 is the report day) and the
    after-hours volume traded before the entry; technical_score counts the conditions met (0-5).

    room_to_resistance_pct is None when no moving average or 52-week high is above the entry price,
    which counts as enough room. The score is None for data collected without moving averages.
    """
    if "sma_200" not in by_offset.columns:
        return {column: None for column in TECHNICAL_COLUMNS}

    report_day = by_offset.loc[-1]
    close = report_day["close"]
    levels = [report_day.get(c) for c in ("sma_20", "sma_50", "sma_200", "high_52w")]
    resistances = [level for level in levels if _present(level) and level > entry_price]
    average_daily_volume = by_offset.loc[by_offset.index < 0, "volume"].mean()
    setup = {
        "close_vs_sma20_pct": (close / report_day["sma_20"] - 1) * 100 if _present(report_day["sma_20"]) else None,
        "run_up_5d_pct": (close / by_offset.at[-5, "close"] - 1) * 100 if -5 in by_offset.index else None,
        "room_to_resistance_pct": (min(resistances) / entry_price - 1) * 100 if resistances else None,
        "ah_vol_vs_adv": after_hours_volume / average_daily_volume if average_daily_volume else None,
        "close_vs_sma200_pct": (close / report_day["sma_200"] - 1) * 100 if _present(report_day["sma_200"]) else None,
        "pct_below_52w_high": (1 - close / report_day["high_52w"]) * 100 if _present(report_day.get("high_52w")) else None,
    }
    conditions = [
        _present(setup["close_vs_sma20_pct"]) and setup["close_vs_sma20_pct"] > 0,
        _present(setup["run_up_5d_pct"]) and setup["run_up_5d_pct"] > 0,
        not resistances or setup["room_to_resistance_pct"] > MIN_ROOM_TO_RESISTANCE_PCT,
        _present(setup["ah_vol_vs_adv"]) and setup["ah_vol_vs_adv"] >= MIN_AFTER_HOURS_VOLUME_VS_ADV,
        _present(setup["close_vs_sma200_pct"]) and setup["close_vs_sma200_pct"] < MAX_ABOVE_SMA200_PCT,
    ]
    setup["technical_score"] = sum(conditions)
    return setup


def summarize_by_technical_score(trades: pd.DataFrame, labels: List[str]) -> pd.DataFrame:
    """Returns at the open, the last intraday exit and the day-0 close, by technical score bucket."""
    last_intraday = labels[-2]
    summary = []
    for bucket, low, high in TECHNICAL_SCORE_BUCKETS:
        g = trades[trades["technical_score"].between(low, high)]
        if g.empty:
            continue
        row = {"technical_score": bucket, "trades": len(g)}
        for label in (AUCTION_OPEN_LABEL, last_intraday, DAY0_CLOSE_LABEL):
            returns = g[label].dropna()
            row[f"win_pct ({label})"] = (returns > 0).mean() * 100
            row[f"avg_pct ({label})"] = returns.mean()
            row[f"median_pct ({label})"] = returns.median()
        summary.append(row)
    return pd.DataFrame(summary).set_index("technical_score") if summary else pd.DataFrame()


def earnings_results(event: Dict) -> Dict:
    """EPS and revenue (in $M) estimate vs actual, with surprise %; positive surprise is a beat.
    *_vs_usual_pts compare the surprise with the company's usual (median of its previous releases)."""
    revenue_estimate, revenue_actual = event.get("revenue_estimate"), event.get("revenue_actual")
    eps_surprise = surprise_pct(event.get("eps_actual"), event.get("eps_estimate"))
    revenue_surprise = surprise_pct(revenue_actual, revenue_estimate)
    return {
        "eps_estimate": event.get("eps_estimate"),
        "eps_actual": event.get("eps_actual"),
        "eps_surprise_pct": eps_surprise,
        "revenue_estimate_m": revenue_estimate / 1e6 if revenue_estimate is not None else None,
        "revenue_actual_m": revenue_actual / 1e6 if revenue_actual is not None else None,
        "revenue_surprise_pct": revenue_surprise,
        "eps_vs_usual_pts": _vs_usual(eps_surprise, event.get("usual_eps_surprise_pct"), EPS_SURPRISE_CAP_PCT),
        "revenue_vs_usual_pts": _vs_usual(
            revenue_surprise, event.get("usual_revenue_surprise_pct"), REVENUE_SURPRISE_CAP_PCT
        ),
        "prior_beat_streak": event.get("prior_beat_streak"),
    }


def _vs_usual(surprise: Optional[float], usual: Optional[float], cap: float) -> Optional[float]:
    """This release's surprise (capped like the usual one) minus the company's usual surprise, in points."""
    if surprise is None or usual is None:
        return None
    return max(min(surprise, cap), -cap) - usual


def forecast_revision_table(manifest: Dict) -> Tuple[Optional[pd.DataFrame], str]:
    """Consensus EPS forecasts before and after the latest release, from the collector's manifest.

    Returns:
        Tuple of (one row per forecast period, description of the snapshots) or (None, reason)
    """
    revision = manifest.get("forecast_revision")
    if not revision:
        return None, "no forecast data in collected data; re-run with --collect"
    if not revision.get("available"):
        return None, revision.get("reason", "unavailable")
    table = pd.DataFrame(revision["periods"]).set_index("label").drop(columns="period")
    table = table.rename(
        columns={
            "before": f"before ({revision['before_snapshot']})",
            "after": f"after ({revision['after_snapshot']})",
            "change_pct": "change_pct (before -> current)",
        }
    )
    return table, f"consensus EPS, {revision['source']}"


def release_levels(event: Dict, context_dir: Path) -> Tuple[Optional[pd.DataFrame], Optional[str]]:
    """Report-day extended-hours close and its distance to the 20/50/200-day moving averages and 52-week high/low.

    Moving averages and the 52-week high/low are as of the report day's regular close.

    Returns:
        Tuple of (one row per level with price, % distance from the extended close and role, None)
        or (None, reason)
    """
    files = event.get("files") or {}
    if not files.get("intraday_5min") or not files.get("daily_window"):
        return None, "missing intraday or daily window data"

    daily = pd.read_csv(context_dir / files["daily_window"], parse_dates=["date"], index_col="date")
    report_day = pd.Timestamp(event["release_date"])
    sma_columns = [f"sma_{days}" for days in MOVING_AVERAGE_WINDOWS]
    if report_day not in daily.index:
        return None, "report day is not a trading session"
    if not set(sma_columns) <= set(daily.columns):
        return None, "no moving averages in collected data; re-run with --collect"

    bars = pd.read_csv(context_dir / files["intraday_5min"], parse_dates=["timestamp"], index_col="timestamp")
    mismatch = price_scale_mismatch(bars, report_day.date(), float(daily.at[report_day, "close"]))
    if mismatch:
        return None, mismatch
    extended_close = last_trade_before(
        bars,
        datetime.combine(report_day.date(), AFTER_HOURS_END),
        since=datetime.combine(report_day.date(), AFTER_HOURS_START),
    )
    if extended_close is None:
        return None, "no after-hours trades on the report day"

    regular_close = float(daily.at[report_day, "close"])
    rows = [{"level": "regular close", "price": regular_close}]
    rows += [
        {"level": f"SMA {days}", "price": daily.at[report_day, f"sma_{days}"]}
        for days in MOVING_AVERAGE_WINDOWS
    ]
    rows += [
        {"level": label, "price": daily.at[report_day, column]}
        for label, column in (("52-week high", "high_52w"), ("52-week low", "low_52w"))
        if column in daily.columns
    ]
    levels = pd.DataFrame(rows).dropna(subset=["price"])
    levels["vs_extended_close_pct"] = (levels["price"] / extended_close - 1) * 100
    levels["role"] = levels["vs_extended_close_pct"].map(
        lambda pct: "resistance (potential gain)" if pct > 0 else "support (potential drawdown)"
    )
    levels.loc[levels["level"] == "regular close", "role"] = ""
    levels = pd.concat(
        [pd.DataFrame([{"level": "extended close", "price": extended_close, "vs_extended_close_pct": 0.0, "role": ""}]),
         levels],
        ignore_index=True,
    )
    return levels.set_index("level"), None


def latest_release_levels(
    tickers: List[str], data_dir: Path, as_of: Optional[date]
) -> List[Tuple[str, Dict, Optional[pd.DataFrame], Optional[str]]]:
    """Levels for the most recent collected release of each ticker: (ticker, event, levels, skip reason)."""
    results = []
    for ticker in tickers:
        context_dir = find_context_dir(data_dir, ticker, as_of)
        if context_dir is None:
            continue
        events = json.loads((context_dir / "manifest.json").read_text()).get("earnings", [])
        if events:
            levels, reason = release_levels(events[0], context_dir)
            results.append((ticker, events[0], levels, reason))
    return results


def reaction_day_profile(event: Dict, context_dir: Path, check_minutes: int) -> Optional[Dict]:
    """Reaction-session data for one release: daily rows by day offset, regular-session 5-min bars,
    and volume in the first `check_minutes` and for the full day. None when data is missing."""
    files = event.get("files") or {}
    if not files.get("intraday_5min") or not files.get("daily_window"):
        return None
    daily = pd.read_csv(context_dir / files["daily_window"], parse_dates=["date"])
    by_offset = daily.set_index("day_offset")
    if -1 not in by_offset.index or 0 not in by_offset.index:
        return None

    reaction_day = by_offset.at[0, "date"].date()
    market_open = datetime.combine(reaction_day, MARKET_OPEN)
    bars = pd.read_csv(context_dir / files["intraday_5min"], parse_dates=["timestamp"], index_col="timestamp")
    session = bars[(bars.index >= market_open) & (bars.index < datetime.combine(reaction_day, AFTER_HOURS_START))]
    if session.empty or price_scale_mismatch(bars, reaction_day, float(by_offset.at[0, "close"])):
        return None
    return {
        "event": event,
        "by_offset": by_offset,
        "session": session,
        "market_open": market_open,
        "early_volume": session.loc[session.index < market_open + timedelta(minutes=check_minutes), "volume"].sum(),
        "day_volume": by_offset.at[0, "volume"],
    }


def gap_follow_through(
    profile: Dict, prior_profiles: List[Dict], opening_range_minutes: int, check_minutes: int
) -> Optional[Dict]:
    """Setup signals and day-0/T+1/T+5 outcomes for a gap-up reaction session.

    Volume is compared only against earlier earnings reaction days, so nothing from later
    releases leaks into the signal. None when there were no trades in the opening range.
    """
    by_offset, session, market_open = profile["by_offset"], profile["session"], profile["market_open"]
    prior_close, day_open = by_offset.at[-1, "close"], by_offset.at[0, "open"]
    before = by_offset[by_offset.index < 0]
    avg_range_pct = ((before["high"] - before["low"]) / before["close"]).mean() * 100
    gap_pct = (day_open / prior_close - 1) * 100

    or_end = market_open + timedelta(minutes=opening_range_minutes)
    opening, after = session[session.index < or_end], session[session.index >= or_end]
    if opening.empty:
        return None
    or_high, or_low = opening["high"].max(), opening["low"].min()
    or_end_price = opening["close"].iloc[-1]

    early = session[session.index < market_open + timedelta(minutes=check_minutes)]
    vwap_prices = early["vwap"] if "vwap" in early.columns else (early["high"] + early["low"] + early["close"]) / 3
    early_vwap = (vwap_prices * early["volume"]).sum() / early["volume"].sum() if early["volume"].sum() else None

    prior_early = [p["early_volume"] for p in prior_profiles if p["early_volume"]]
    prior_day = [p["day_volume"] for p in prior_profiles if p["day_volume"]]
    high_52w = by_offset.at[-1, "high_52w"] if "high_52w" in by_offset.columns else None
    low_52w = by_offset.at[-1, "low_52w"] if "low_52w" in by_offset.columns else None
    day0_close = by_offset.at[0, "close"]

    return {
        "release_date": profile["event"]["release_date"],
        "timing": profile["event"].get("timing"),
        "gap_pct": gap_pct,
        "gap_x_avg_range": gap_pct / avg_range_pct if avg_range_pct else None,
        "or_width_pct": (or_high / or_low - 1) * 100,
        "or_break": _first_break(after, or_high, or_low),
        "early_vol_vs_prior_earnings": profile["early_volume"] / _mean(prior_early) if prior_early else None,
        "day_vol_vs_prior_earnings": profile["day_volume"] / _mean(prior_day) if prior_day else None,
        "vs_vwap_at_check_pct": (early["close"].iloc[-1] / early_vwap - 1) * 100 if early_vwap else None,
        "to_52w_high_pct": (high_52w / day_open - 1) * 100 if _present(high_52w) else None,
        "above_52w_low_pct": (day_open / low_52w - 1) * 100 if _present(low_52w) else None,
        "high_from_open_pct": (by_offset.at[0, "high"] / day_open - 1) * 100,
        "low_from_open_pct": (by_offset.at[0, "low"] / day_open - 1) * 100,
        "close_from_open_pct": (day0_close / day_open - 1) * 100,
        "or_end_to_close_pct": (day0_close / or_end_price - 1) * 100,
        "check_to_close_pct": (day0_close / early["close"].iloc[-1] - 1) * 100,
        "t1_pct": (by_offset.at[1, "close"] / day0_close - 1) * 100 if 1 in by_offset.index else None,
        "t5_pct": (by_offset.at[5, "close"] / day0_close - 1) * 100 if 5 in by_offset.index else None,
    }


def collect_follow_through(
    tickers: List[str],
    data_dir: Path,
    as_of: Optional[date],
    min_gap_pct: float,
    opening_range_minutes: int,
    check_minutes: int,
) -> pd.DataFrame:
    """One row per release whose reaction session gapped up by at least `min_gap_pct`."""
    rows = []
    for ticker in tickers:
        context_dir = find_context_dir(data_dir, ticker, as_of)
        if context_dir is None:
            continue
        events = json.loads((context_dir / "manifest.json").read_text()).get("earnings", [])
        # with unknown timing the reaction session is ambiguous (release day or the day after)
        known = [e for e in events if e.get("timing") in ("amc", "bmo")]
        profiles = [p for p in (reaction_day_profile(e, context_dir, check_minutes) for e in known) if p]
        for profile in profiles:
            release = profile["event"]["release_date"]
            by_offset = profile["by_offset"]
            if (by_offset.at[0, "open"] / by_offset.at[-1, "close"] - 1) * 100 < min_gap_pct:
                continue
            prior = [p for p in profiles if p["event"]["release_date"] < release]
            result = gap_follow_through(profile, prior, opening_range_minutes, check_minutes)
            if result is not None:
                rows.append({"ticker": ticker, **result})
    return pd.DataFrame(rows)


def summarize_follow_through(follow: pd.DataFrame, check_minutes: int) -> pd.DataFrame:
    """Day-0 and next-day outcomes grouped by each setup signal."""
    groups = {"all gap-ups": follow.index == follow.index}
    for direction in ("up", "down", "none"):
        groups[f"opening range broke {direction}"] = follow["or_break"] == direction
    for low, high in GAP_BUCKETS:
        if high == float("inf"):
            label = f"gap >{low:g}%"
        else:
            label = f"gap {low:g}-{high:g}%" if low else f"gap <={high:g}%"
        groups[label] = (follow["gap_pct"] > low) & (follow["gap_pct"] <= high)
    groups[f"first {check_minutes}m volume > prior earnings days"] = follow["early_vol_vs_prior_earnings"] > 1
    groups[f"first {check_minutes}m volume <= prior earnings days"] = follow["early_vol_vs_prior_earnings"] <= 1
    groups[f"above VWAP at +{check_minutes}m"] = follow["vs_vwap_at_check_pct"] > 0
    groups[f"below VWAP at +{check_minutes}m"] = follow["vs_vwap_at_check_pct"] <= 0
    groups["opened above 52-week high"] = follow["to_52w_high_pct"] <= 0
    groups["opened below 52-week high"] = follow["to_52w_high_pct"] > 0

    summary = []
    for label, mask in groups.items():
        g = follow[mask]
        if g.empty:
            continue
        summary.append(
            {
                "signal": label,
                "releases": len(g),
                "close_above_open_pct": (g["close_from_open_pct"] > 0).mean() * 100,
                "avg_close_from_open_pct": g["close_from_open_pct"].mean(),
                "avg_or_end_to_close_pct": g["or_end_to_close_pct"].mean(),
                "avg_check_to_close_pct": g["check_to_close_pct"].mean(),
                "avg_high_from_open_pct": g["high_from_open_pct"].mean(),
                "avg_low_from_open_pct": g["low_from_open_pct"].mean(),
                "avg_t1_pct": g["t1_pct"].mean(),
            }
        )
    return pd.DataFrame(summary).set_index("signal")


def collect_contexts(
    tickers: List[str], data_dir: Path, as_of: Optional[date], quarters: int, workers: int, resume: bool
) -> List[Tuple[str, str]]:
    """Run the earnings price context collector for each ticker; returns (ticker, error) for failures."""
    collector = EarningsPriceContextCollector(output_dir=str(data_dir), as_of=as_of)
    if resume:
        tickers = [t for t in tickers if find_context_dir(data_dir, t, collector.as_of) is None]
    failures = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(collector.collect, ticker, quarters): ticker for ticker in tickers}
        for done, future in enumerate(as_completed(futures), start=1):
            ticker = futures[future]
            try:
                future.result()
            except Exception as e:
                failures.append((ticker, str(e)))
            if done % 50 == 0 or done == len(futures):
                print(f"collected {done}/{len(futures)} tickers ({len(failures)} failed)", flush=True)
    return failures


def _first_break(bars: pd.DataFrame, high: float, low: float) -> str:
    for _, bar in bars.iterrows():
        if bar["high"] > high:
            return "up"
        if bar["low"] < low:
            return "down"
    return "none"


def _mean(values: List[float]) -> float:
    return sum(values) / len(values)


def _present(value) -> bool:
    return value is not None and not pd.isna(value)


def load_market_caps(tickers: List[str], data_dir: Path, as_of: Optional[date]) -> Dict[str, float]:
    """Market cap in $B per ticker: from the collector's manifest, else a batched FMP quote lookup.

    This is the market cap at collection time, not on each release date.
    """
    caps, missing = {}, []
    for ticker in tickers:
        context_dir = find_context_dir(data_dir, ticker, as_of)
        manifest = json.loads((context_dir / "manifest.json").read_text()) if context_dir else {}
        if manifest.get("market_cap_b"):
            caps[ticker] = manifest["market_cap_b"]
        else:
            missing.append(ticker)
    if missing:
        caps.update(FinancialDataFetcher().get_market_caps(missing))
        unknown = [t for t in missing if t not in caps]
        if unknown:
            logger.warning(f"No market cap for {len(unknown)} tickers (dropped by market-cap filters): {', '.join(unknown[:10])}"
                           + (" ..." if len(unknown) > 10 else ""))
    return caps


def filter_trades(
    trades: pd.DataFrame,
    minimums: Optional[Dict[str, Optional[float]]] = None,
    maximums: Optional[Dict[str, Optional[float]]] = None,
) -> pd.DataFrame:
    """Keep trades whose column values are above each minimum and at most each maximum, e.g.
    minimums={"eps_surprise_pct": 0} keeps EPS beats and maximums={"pct_below_52w_high": 5} keeps
    report-day closes within 5% of the 52-week high. Limits of None are ignored; trades missing a
    filtered value are dropped."""
    keep = pd.Series(True, index=trades.index)
    for column, limit in (minimums or {}).items():
        if limit is not None:
            keep &= trades[column].notna() & (trades[column] > limit)
    for column, limit in (maximums or {}).items():
        if limit is not None:
            keep &= trades[column].notna() & (trades[column] <= limit)
    return trades[keep]


def to_short(trades: pd.DataFrame, labels: List[str]) -> pd.DataFrame:
    """Convert long returns to short returns: the stock's fall is the gain. The short's peak (best)
    is the stock's lowest low and its low (worst) is the stock's highest high."""
    short = trades.copy()
    for label in labels:
        short[label] = -trades[label]
        peak, low = f"{PEAK_PREFIX}{label}", f"{LOW_PREFIX}{label}"
        if peak in trades:
            short[peak], short[low] = -trades[low], -trades[peak]
    return short


def collect_trades(
    tickers: List[str],
    data_dir: Path,
    as_of: Optional[date],
    entry_minutes_before_close: int,
    max_minutes: int,
    interval: int,
    max_entry_staleness: Optional[float] = None,
) -> Tuple[pd.DataFrame, List[Tuple[str, str, str]]]:
    """Simulate trades for every collected release of every ticker.

    Returns:
        Tuple of (one row per trade with entry and per-exit return columns, skipped (ticker, release, reason))
    """
    rows, skipped = [], []
    for ticker in tickers:
        context_dir = find_context_dir(data_dir, ticker, as_of)
        if context_dir is None:
            skipped.append((ticker, "-", f"no collected data in {data_dir / ticker}"))
            continue
        manifest = json.loads((context_dir / "manifest.json").read_text())
        for event in manifest.get("earnings", []):
            trade, reason = simulate_trade(
                event, context_dir, entry_minutes_before_close, max_minutes, interval, max_entry_staleness
            )
            if trade is None:
                skipped.append((ticker, event.get("release_date", "-"), reason))
                continue
            rows.append(
                {
                    "ticker": ticker,
                    "release_date": trade["release_date"],
                    "entry_time": trade["entry_time"],
                    "regular_close": trade["regular_close"],
                    "entry_price": trade["entry_price"],
                    "entry_staleness_min": trade["entry_staleness_min"],
                    **trade["earnings"],
                    **trade["technical"],
                    **trade["returns_pct"],
                    **{f"{PEAK_PREFIX}{label}": pct for label, pct in trade["peaks_pct"].items()},
                    **{f"{LOW_PREFIX}{label}": pct for label, pct in trade["lows_pct"].items()},
                }
            )
    return pd.DataFrame(rows), skipped


def summarize(trades: pd.DataFrame, labels: List[str]) -> pd.DataFrame:
    """Win probability and return statistics for each exit time, plus the average peak and low
    reached between the open and that time (all % vs the entry price)."""
    summary = []
    for label in labels:
        returns = trades[label].dropna() if label in trades else pd.Series(dtype=float)
        peaks = trades.get(f"{PEAK_PREFIX}{label}", pd.Series(dtype=float)).dropna()
        lows = trades.get(f"{LOW_PREFIX}{label}", pd.Series(dtype=float)).dropna()
        summary.append(
            {
                "exit": label,
                "trades": len(returns),
                "win_rate_pct": (returns > 0).mean() * 100 if len(returns) else None,
                "avg_return_pct": returns.mean() if len(returns) else None,
                "median_return_pct": returns.median() if len(returns) else None,
                "best_pct": returns.max() if len(returns) else None,
                "worst_pct": returns.min() if len(returns) else None,
                "avg_peak_pct": peaks.mean() if len(peaks) else None,
                "avg_low_pct": lows.mean() if len(lows) else None,
            }
        )
    return pd.DataFrame(summary).set_index("exit")


def _read_tickers(tickers: List[str], tickers_file: Optional[str]) -> List[str]:
    if tickers_file:
        lines = Path(tickers_file).read_text().splitlines()
        tickers = tickers + [t.strip() for t in lines if t.strip() and not t.startswith("#")]
    return list(dict.fromkeys(t.upper() for t in tickers))


def main():
    parser = argparse.ArgumentParser(description="Backtest buying after-hours post-earnings and selling after the next open")
    parser.add_argument("tickers", nargs="*", help="Ticker symbols, e.g. MDB CRWD")
    parser.add_argument("--tickers-file", help="File with one ticker per line")
    parser.add_argument("--quarters", type=int, default=4, help="Past releases to collect with --collect (default: 4)")
    parser.add_argument("--collect", action="store_true", help="Collect earnings price context before backtesting")
    parser.add_argument("--data-dir", type=Path, help="Collector output root (default: <DATA_DIR>/earnings_price_context)")
    parser.add_argument("--as-of", type=date.fromisoformat, help="Use data collected on this date (default: latest)")
    parser.add_argument("--entry-minutes-before-close", type=int, default=15,
                        help="Buy this many minutes before the 20:00 ET after-hours close; multiple of 5 (default: 15)")
    parser.add_argument("--max-entry-staleness", type=float,
                        help="Skip trades whose last after-hours trade ended more than this many minutes before the entry")
    parser.add_argument("--short", action="store_true",
                        help="Reverse trade: short at the entry and buy back at each exit")
    parser.add_argument("--max-pct-below-52w-high", type=float,
                        help="Only releases whose report-day close is within this %% of the 52-week high")
    parser.add_argument("--min-pct-below-52w-high", type=float,
                        help="Only releases whose report-day close is more than this %% below the 52-week high")
    parser.add_argument("--max-eps-surprise", type=float,
                        help="Only releases with EPS surprise at most this %% (e.g. -5 for a miss of 5%% or more)")
    parser.add_argument("--max-revenue-surprise", type=float,
                        help="Only releases with revenue surprise at most this %% (e.g. -2 for a miss of 2%% or more)")
    parser.add_argument("--min-market-cap", type=float,
                        help="Only tickers with market cap above this many $B (current, at collection time)")
    parser.add_argument("--max-market-cap", type=float,
                        help="Only tickers with market cap at most this many $B (current, at collection time)")
    parser.add_argument("--min-eps-surprise", type=float,
                        help="Only releases with EPS surprise above this %% (0 keeps beats)")
    parser.add_argument("--min-revenue-surprise", type=float,
                        help="Only releases with revenue surprise above this %% (0 keeps beats)")
    parser.add_argument("--min-ah-move-x-range", type=float,
                        help="Only trades whose after-hours move is above this many average daily ranges")
    parser.add_argument("--max-ah-move-x-range", type=float,
                        help="Only trades whose after-hours move is at most this many average daily ranges")
    parser.add_argument("--min-eps-vs-usual", type=float,
                        help="Only releases whose EPS surprise beats the company's usual surprise by more than this many points")
    parser.add_argument("--min-revenue-vs-usual", type=float,
                        help="Only releases whose revenue surprise beats the company's usual surprise by more than this many points")
    parser.add_argument("--min-after-hours-move", type=float,
                        help="Only trades whose after-hours move (entry vs regular close) is above this %%")
    parser.add_argument("--max-after-hours-move", type=float,
                        help="Only trades whose after-hours move (entry vs regular close) is at most this %%")
    parser.add_argument("--max-minutes", type=int, default=40, help="Last exit, minutes after the open (default: 40)")
    parser.add_argument("--interval", type=int, default=5, help="Minutes between exits; multiple of 5 (default: 5)")
    parser.add_argument("--min-gap", type=float, default=2.0,
                        help="Gap follow-through: minimum day-0 gap up in %% (default: 2)")
    parser.add_argument("--opening-range-minutes", type=int, default=10,
                        help="Gap follow-through: opening range length; multiple of 5 (default: 10)")
    parser.add_argument("--check-minutes", type=int, default=30,
                        help="Gap follow-through: minutes after the open for the volume and VWAP checks (default: 30)")
    parser.add_argument("--workers", type=int, default=1, help="Tickers to collect in parallel with --collect (default: 1)")
    parser.add_argument("--resume", action="store_true", help="With --collect, skip tickers already collected for --as-of")
    parser.add_argument("--summary-only", action="store_true", help="Print only summary tables, not per-release rows")
    parser.add_argument("--output", help="Write per-trade returns to this CSV file (and gap follow-through to <name>_follow_through.csv)")
    args = parser.parse_args()

    for name in ("interval", "opening_range_minutes", "check_minutes", "entry_minutes_before_close"):
        if getattr(args, name) % 5 or getattr(args, name) <= 0:
            parser.error(f"--{name.replace('_', '-')} must be a positive multiple of 5 (bars are 5 minutes)")

    logging.basicConfig(level=logging.WARNING, format="%(levelname)s - %(message)s")
    tickers = _read_tickers(args.tickers, args.tickers_file)
    if not tickers:
        parser.error("provide at least one ticker or --tickers-file")

    data_dir = args.data_dir or default_data_dir()
    collect_failures = []
    if args.collect:
        collect_failures = collect_contexts(tickers, data_dir, args.as_of, args.quarters, args.workers, args.resume)

    labels = exit_labels(args.max_minutes, args.interval)
    trades, skipped = collect_trades(
        tickers, data_dir, args.as_of, args.entry_minutes_before_close, args.max_minutes, args.interval,
        args.max_entry_staleness,
    )
    collected = len(trades)
    if not trades.empty:
        if args.min_market_cap is not None or args.max_market_cap is not None:
            caps = load_market_caps(sorted(trades["ticker"].unique()), data_dir, args.as_of)
            trades["market_cap_b"] = trades["ticker"].map(caps)
        trades = filter_trades(
            trades,
            minimums={
                "after_hours_move_pct": args.min_after_hours_move,
                "pct_below_52w_high": args.min_pct_below_52w_high,
                "market_cap_b": args.min_market_cap,
                "eps_surprise_pct": args.min_eps_surprise,
                "revenue_surprise_pct": args.min_revenue_surprise,
                "ah_move_x_range": args.min_ah_move_x_range,
                "eps_vs_usual_pts": args.min_eps_vs_usual,
                "revenue_vs_usual_pts": args.min_revenue_vs_usual,
            },
            maximums={
                "after_hours_move_pct": args.max_after_hours_move,
                "pct_below_52w_high": args.max_pct_below_52w_high,
                "market_cap_b": args.max_market_cap,
                "eps_surprise_pct": args.max_eps_surprise,
                "revenue_surprise_pct": args.max_revenue_surprise,
                "ah_move_x_range": args.max_ah_move_x_range,
            },
        )
        if args.short:
            trades = to_short(trades, labels)

    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 50)
    if trades.empty:
        print(f"No trades to evaluate ({collected} collected, none pass the filters)." if collected else "No trades to evaluate.")
    else:
        action = ("short", "buy back") if args.short else ("buy", "sell")
        print(f"Overnight earnings trade: {action[0]} {args.entry_minutes_before_close} min before after-hours close, "
              f"{action[1]} after next open (returns in %)")
        if len(trades) < collected:
            print(f"{len(trades)} of {collected} trades pass the filters")
        print()
        if not args.summary_only:
            indexed = trades.set_index(["ticker", "release_date"])
            print("Earnings results (surprise % > 0 is a beat; after_hours_move_pct is entry price vs regular close):")
            print(indexed[EARNINGS_COLUMNS].round(2).to_string())
            print("\nTechnical setup at entry (score = conditions met: above SMA20, 5d run-up > 0, "
                  f"room to resistance > {MIN_ROOM_TO_RESISTANCE_PCT:g}% or none, AH volume >= "
                  f"{MIN_AFTER_HOURS_VOLUME_VS_ADV:g}x ADV, < {MAX_ABOVE_SMA200_PCT:g}% above SMA200):")
            print(indexed[TECHNICAL_COLUMNS].round(2).to_string())
            print("\nPer trade returns:")
            print(indexed[["entry_time", "entry_staleness_min", "regular_close", "entry_price"] + labels].round(2).to_string())
            after_open = path_labels(labels)
            for title, prefix in (("Peak", PEAK_PREFIX), ("Low", LOW_PREFIX)):
                print(f"\n{title} since the open (% vs entry; highest high / lowest low from 9:30 up to each sell time, "
                      "full session for day-0 close):")
                table = indexed[[f"{prefix}{label}" for label in after_open]]
                print(table.set_axis(after_open, axis=1).round(2).to_string())
        print(f"\nSummary by exit time ({len(trades)} trades):")
        print(summarize(trades, labels).round(2).to_string())
        by_score = summarize_by_technical_score(trades, labels)
        if not by_score.empty:
            print("\nBy technical score (with a beat + raised guidance, score >= 3 favored holding past the open):")
            print(by_score.round(2).T.to_string())
        if trades["ticker"].nunique() > 1 and not args.summary_only:
            print("\nWin rate % by ticker:")
            print(trades.groupby("ticker")[labels].agg(lambda r: (r.dropna() > 0).mean() * 100).round(0).to_string())

    for ticker, event, levels, reason in ([] if args.summary_only else latest_release_levels(tickers, data_dir, args.as_of)):
        print(f"\nLatest release levels: {ticker} {event['release_date']} ({event.get('timing')}), "
              f"distance from the report-day extended close")
        if levels is None:
            print(f"  unavailable: {reason}")
        else:
            print(levels.round(2).to_string())
        context_dir = find_context_dir(data_dir, ticker, args.as_of)
        revision, description = forecast_revision_table(json.loads((context_dir / "manifest.json").read_text()))
        print(f"\nForecast revision across the latest release: {ticker} ({description if revision is not None else 'unavailable'})")
        if revision is None:
            print(f"  {description}")
        else:
            print(revision.round(4).to_string())

    follow = collect_follow_through(
        tickers, data_dir, args.as_of, args.min_gap, args.opening_range_minutes, args.check_minutes
    )
    print(f"\nGap follow-through: reaction sessions that gapped up >= {args.min_gap:g}% "
          f"(opening range = first {args.opening_range_minutes}m; volume/VWAP checks at +{args.check_minutes}m)")
    if follow.empty:
        print("  no gap-up releases")
    else:
        if not args.summary_only:
            indexed = follow.set_index(["ticker", "release_date"])
            print("Setup (gap_x_avg_range = gap / avg daily range of the 5 sessions before; "
                  "volume ratios vs earlier earnings days only):")
            print(indexed[FOLLOW_THROUGH_SETUP_COLUMNS].round(2).to_string())
            print("\nOutcome (% from day-0 open unless noted; or_end_to_close / check_to_close from the price at the end "
                  f"of the opening range / at +{args.check_minutes}m; t1/t5 from day-0 close):")
            print(indexed[FOLLOW_THROUGH_OUTCOME_COLUMNS].round(2).to_string())
        print(f"\nFollow-through by signal ({len(follow)} gap-ups):")
        print(summarize_follow_through(follow, args.check_minutes).round(2).to_string())

    if collect_failures:
        print(f"\nCollection failed for {len(collect_failures)} tickers:")
        for ticker, error in collect_failures:
            print(f"  {ticker}: {error}")
    if skipped and not args.summary_only:
        print("\nSkipped:")
        for ticker, release, reason in skipped:
            print(f"  {ticker} {release}: {reason}")
    elif skipped:
        print(f"\nSkipped {len(skipped)} releases (before-open/unknown timing or missing data); omit --summary-only for details")

    if args.output and not trades.empty:
        trades.to_csv(args.output, index=False)
        print(f"\nWrote per-trade returns to {args.output}")
    if args.output and not follow.empty:
        follow_path = Path(args.output).with_name(f"{Path(args.output).stem}_follow_through.csv")
        follow.to_csv(follow_path, index=False)
        print(f"Wrote gap follow-through to {follow_path}")


if __name__ == "__main__":
    main()
