"""Backtest an overnight earnings trade from collected earnings price context.

Strategy, for each after-close (amc) earnings release:
- Buy N minutes before the after-hours session closes (default 19:45 ET) on the release day
- Sell the next morning at the market open, or at each 5-min mark up to M minutes after the open

Prices are the last trade before each time, taken from the collector's 5-min bars
(earnings/<release_date>/intraday_5min.csv). The "open" exit is the first regular-session
trade; "open (auction)" is the official opening price from the daily candle.

Before-open (bmo) releases are skipped: the evening before, earnings are not reported yet.

For the latest release of each ticker it also reports the report day's extended-hours close
and its distance to the 20/50/200-day moving averages: a moving average above that price is
resistance (potential gain to reach it), one below is support (potential drawdown to reach it).

Usage:
    python over_night_eraning_trade.py MDB --collect
    python over_night_eraning_trade.py MDB CRWD SNOW --max-minutes 60 --interval 5 --output trades.csv
"""

import argparse
import json
import logging
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

from financial_analysis_agent.config import get_config
from financial_analysis_agent.financial.earnings_price_context import (
    MOVING_AVERAGE_WINDOWS,
    EarningsPriceContextCollector,
)

logger = logging.getLogger(__name__)

AFTER_HOURS_START = time(16, 0)
AFTER_HOURS_END = time(20, 0)
MARKET_OPEN = time(9, 30)
AUCTION_OPEN_LABEL = "open (auction)"
FIRST_TRADE_OPEN_LABEL = "open"


def default_data_dir() -> Path:
    return Path(get_config().get("paths.data")) / "earnings_price_context"


def exit_labels(max_minutes: int, interval: int) -> List[str]:
    return [AUCTION_OPEN_LABEL, FIRST_TRADE_OPEN_LABEL] + [
        f"+{m}m" for m in range(interval, max_minutes + 1, interval)
    ]


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


def first_trade_at_or_after(bars: pd.DataFrame, moment: datetime, until: datetime) -> Optional[float]:
    window = bars[(bars.index >= moment) & (bars.index < until)]
    return float(window["open"].iloc[0]) if not window.empty else None


def simulate_trade(
    event: Dict,
    context_dir: Path,
    entry_minutes_before_close: int,
    max_minutes: int,
    interval: int,
) -> Tuple[Optional[Dict], Optional[str]]:
    """Simulate the overnight trade for one earnings release.

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

    entry_time = datetime.combine(entry_day, AFTER_HOURS_END) - timedelta(minutes=entry_minutes_before_close)
    entry_price = last_trade_before(bars, entry_time, since=datetime.combine(entry_day, AFTER_HOURS_START))
    if entry_price is None:
        return None, f"no after-hours trades on {entry_day} before {entry_time:%H:%M}"

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

    trade = {
        "release_date": event["release_date"],
        "entry_time": entry_time.strftime("%Y-%m-%d %H:%M"),
        "entry_price": entry_price,
        "regular_close": float(by_offset.at[-1, "close"]),
        "eps_surprise_pct": _surprise_pct(event.get("eps_actual"), event.get("eps_estimate")),
        "exit_prices": exits,
        "returns_pct": {
            label: (price / entry_price - 1) * 100 if price is not None else None
            for label, price in exits.items()
        },
    }
    return trade, None


def release_levels(event: Dict, context_dir: Path) -> Tuple[Optional[pd.DataFrame], Optional[str]]:
    """Report-day extended-hours close and its distance to the 20/50/200-day moving averages.

    Moving averages are as of the report day's regular close.

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


def collect_trades(
    tickers: List[str],
    data_dir: Path,
    as_of: Optional[date],
    entry_minutes_before_close: int,
    max_minutes: int,
    interval: int,
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
            trade, reason = simulate_trade(event, context_dir, entry_minutes_before_close, max_minutes, interval)
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
                    "eps_surprise_pct": trade["eps_surprise_pct"],
                    **trade["returns_pct"],
                }
            )
    return pd.DataFrame(rows), skipped


def summarize(trades: pd.DataFrame, labels: List[str]) -> pd.DataFrame:
    """Win probability and return statistics for each exit time."""
    summary = []
    for label in labels:
        returns = trades[label].dropna() if label in trades else pd.Series(dtype=float)
        summary.append(
            {
                "exit": label,
                "trades": len(returns),
                "win_rate_pct": (returns > 0).mean() * 100 if len(returns) else None,
                "avg_return_pct": returns.mean() if len(returns) else None,
                "median_return_pct": returns.median() if len(returns) else None,
                "best_pct": returns.max() if len(returns) else None,
                "worst_pct": returns.min() if len(returns) else None,
            }
        )
    return pd.DataFrame(summary).set_index("exit")


def _surprise_pct(actual, estimate) -> Optional[float]:
    if actual is None or estimate in (None, 0):
        return None
    return (actual / estimate - 1) * 100 * (1 if estimate > 0 else -1)


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
                        help="Buy this many minutes before the 20:00 ET after-hours close (default: 15)")
    parser.add_argument("--max-minutes", type=int, default=40, help="Last exit, minutes after the open (default: 40)")
    parser.add_argument("--interval", type=int, default=5, help="Minutes between exits; multiple of 5 (default: 5)")
    parser.add_argument("--output", help="Write per-trade returns to this CSV file")
    args = parser.parse_args()

    if args.interval % 5 or args.interval <= 0:
        parser.error("--interval must be a positive multiple of 5 (bars are 5 minutes)")

    logging.basicConfig(level=logging.WARNING, format="%(levelname)s - %(message)s")
    tickers = _read_tickers(args.tickers, args.tickers_file)
    if not tickers:
        parser.error("provide at least one ticker or --tickers-file")

    data_dir = args.data_dir or default_data_dir()
    if args.collect:
        collector = EarningsPriceContextCollector(output_dir=str(data_dir), as_of=args.as_of)
        for ticker in tickers:
            collector.collect(ticker, args.quarters)

    labels = exit_labels(args.max_minutes, args.interval)
    trades, skipped = collect_trades(
        tickers, data_dir, args.as_of, args.entry_minutes_before_close, args.max_minutes, args.interval
    )

    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 50)
    if trades.empty:
        print("No trades to evaluate.")
    else:
        print(f"Overnight earnings trade: buy {args.entry_minutes_before_close} min before after-hours close, "
              f"sell after next open (returns in %)\n")
        print("Per trade:")
        print(trades.set_index(["ticker", "release_date"]).round(2).to_string())
        print(f"\nSummary by exit time ({len(trades)} trades):")
        print(summarize(trades, labels).round(2).to_string())
        if trades["ticker"].nunique() > 1:
            print("\nWin rate % by ticker:")
            print(trades.groupby("ticker")[labels].agg(lambda r: (r.dropna() > 0).mean() * 100).round(0).to_string())

    for ticker, event, levels, reason in latest_release_levels(tickers, data_dir, args.as_of):
        print(f"\nLatest release levels: {ticker} {event['release_date']} ({event.get('timing')}), "
              f"distance from the report-day extended close")
        if levels is None:
            print(f"  unavailable: {reason}")
        else:
            print(levels.round(2).to_string())

    if skipped:
        print("\nSkipped:")
        for ticker, release, reason in skipped:
            print(f"  {ticker} {release}: {reason}")

    if args.output and not trades.empty:
        trades.to_csv(args.output, index=False)
        print(f"\nWrote per-trade returns to {args.output}")


if __name__ == "__main__":
    main()
