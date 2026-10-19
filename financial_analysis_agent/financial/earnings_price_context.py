"""Collect price data around a stock's earnings releases and store it as files on disk.

For each ticker this produces:
- Daily candles for the last 90 calendar days
- Sector ETF / SPY performance over the last quarter (63 trading days)
- For each of the last N reported earnings releases:
    - Daily candles from T-5 to T+10 trading days (with 20/50/200-day SMAs, 52-week high/low,
      and sector ETF and SPY closes)
    - 5-minute candles, including extended hours, from T-2 to T+2 trading days
- Consensus EPS forecast revision across the latest release (when it is within 90 days)

Day T (offset 0) is the reaction session: the release date itself for releases
before the open, the next trading day for releases after the close.
"""

import argparse
import json
import logging
from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from ..config import get_config
from .data_fetcher import FinancialDataFetcher

logger = logging.getLogger(__name__)

SECTOR_ETFS = {
    "Technology": "XLK",
    "Healthcare": "XLV",
    "Financial Services": "XLF",
    "Consumer Cyclical": "XLY",
    "Consumer Defensive": "XLP",
    "Energy": "XLE",
    "Industrials": "XLI",
    "Basic Materials": "XLB",
    "Real Estate": "XLRE",
    "Utilities": "XLU",
    "Communication Services": "XLC",
}
BENCHMARK_ETF = "SPY"

DAILY_LOOKBACK_CALENDAR_DAYS = 90
SECTOR_LOOKBACK_TRADING_DAYS = 63
WINDOW_DAYS_BEFORE = 5
WINDOW_DAYS_AFTER = 10
INTRADAY_DAYS_AROUND = 2
INTRADAY_INTERVAL_MINUTES = 5
HISTORY_CALENDAR_DAYS = 800  # 4 quarters back plus a 52-week lookback
MOVING_AVERAGE_WINDOWS = (20, 50, 200)
FIFTY_TWO_WEEK_SESSIONS = 252
EPS_TREND_SNAPSHOT_AGES = {"current": 0, "7daysAgo": 7, "30daysAgo": 30, "60daysAgo": 60, "90daysAgo": 90}
EPS_TREND_PERIODS = {
    "0q": "next quarter",
    "+1q": "quarter after next",
    "0y": "current fiscal year",
    "+1y": "next fiscal year",
}
TRADING_DAYS_PER_YEAR = 252
EXTENDED_HOURS_START = time(4, 0)
EXTENDED_HOURS_END = time(20, 0)
MARKET_OPEN = time(9, 30)
MARKET_CLOSE = time(16, 0)


@dataclass
class EarningsEvent:
    """A single earnings release."""

    release_date: date
    timing: str  # 'bmo', 'amc' or 'unknown'
    fiscal_period_end: Optional[date] = None
    eps_estimate: Optional[float] = None
    eps_actual: Optional[float] = None
    revenue_estimate: Optional[float] = None
    revenue_actual: Optional[float] = None


class EarningsPriceContextCollector:
    """Collects price context around earnings releases and writes it to disk."""

    def __init__(
        self,
        fetcher: Optional[FinancialDataFetcher] = None,
        output_dir: Optional[str] = None,
        as_of: Optional[date] = None,
    ):
        """Initialize the collector.

        Args:
            fetcher: Data fetcher (default: a new FinancialDataFetcher)
            output_dir: Root directory for output files (default: <DATA_DIR>/earnings_price_context)
            as_of: Collection date; data after this date is ignored (default: today)
        """
        self.fetcher = fetcher or FinancialDataFetcher()
        self.output_dir = Path(
            output_dir or Path(get_config().get("paths.data")) / "earnings_price_context"
        )
        self.as_of = as_of or date.today()
        self._daily_cache: Dict[str, pd.DataFrame] = {}

    def resolve_earnings_events(
        self, ticker: str, num_quarters: int = 4
    ) -> Tuple[List[EarningsEvent], Optional[EarningsEvent]]:
        """Get the last reported earnings releases and the next upcoming one.

        FMP is preferred because it provides release timing (bmo/amc) and current dates; it is retried
        once (requests can time out under load) before falling back to yfinance.

        Returns:
            Tuple of (past events, most recent first; upcoming event or None)
        """
        events = self._events_from_fmp(ticker) or self._events_from_fmp(ticker)
        if not events:
            logger.warning(f"No FMP earnings calendar for {ticker}; falling back to yfinance, whose dates may be stale")
            events = self._events_from_yfinance(ticker)
        past = [
            e
            for e in events
            if e.release_date < self.as_of or (e.release_date == self.as_of and e.eps_actual is not None)
        ]
        future = [e for e in events if e not in past]
        past.sort(key=lambda e: e.release_date, reverse=True)
        future.sort(key=lambda e: e.release_date)
        return past[:num_quarters], (future[0] if future else None)

    def get_daily_bars(self, symbol: str) -> pd.DataFrame:
        """Get daily candles for the full history range used by the collector (cached per symbol)."""
        if symbol not in self._daily_cache:
            df = self.fetcher.get_stock_data(
                symbol,
                start_date=self.as_of - timedelta(days=HISTORY_CALENDAR_DAYS),
                end_date=self.as_of + timedelta(days=1),
                interval="1d",
            )
            if df is None:
                df = pd.DataFrame()
            if not df.empty:
                df = df[["open", "high", "low", "close", "volume"]]
                df.index = pd.to_datetime(df.index).normalize()
                df.index.name = "date"
            self._daily_cache[symbol] = df
        return self._daily_cache[symbol]

    def get_daily_history(self, ticker: str) -> pd.DataFrame:
        """Get daily candles for the last 90 calendar days."""
        daily = self.get_daily_bars(ticker)
        start = pd.Timestamp(self.as_of - timedelta(days=DAILY_LOOKBACK_CALENDAR_DAYS))
        return daily[daily.index >= start]

    def get_sector_performance(
        self, ticker: str, sector_etf: Optional[str]
    ) -> Tuple[pd.DataFrame, Dict]:
        """Compare the stock against its sector ETF and SPY over the last quarter.

        Returns:
            Tuple of (daily closes per symbol, summary metrics)
        """
        symbols = [ticker] + [s for s in (sector_etf, BENCHMARK_ETF) if s]
        closes = pd.concat(
            {s: self.get_daily_bars(s)["close"] for s in symbols if not self.get_daily_bars(s).empty},
            axis=1,
        ).dropna(how="all")
        closes = closes.tail(SECTOR_LOOKBACK_TRADING_DAYS + 1)

        returns = {s: _pct_change(closes[s].iloc[0], closes[s].iloc[-1]) for s in closes.columns}
        volatility = {
            s: _round(closes[s].pct_change(fill_method=None).std() * np.sqrt(TRADING_DAYS_PER_YEAR) * 100)
            for s in closes.columns
        }
        summary = {
            "start_date": _date_str(closes.index[0]) if not closes.empty else None,
            "end_date": _date_str(closes.index[-1]) if not closes.empty else None,
            "trading_days": max(len(closes) - 1, 0),
            "sector_etf": sector_etf,
            "return_pct": returns,
            "annualized_volatility_pct": volatility,
            "stock_vs_sector_pct": _diff(returns.get(ticker), returns.get(sector_etf)),
            "sector_vs_market_pct": _diff(returns.get(sector_etf), returns.get(BENCHMARK_ETF)),
            "stock_vs_market_pct": _diff(returns.get(ticker), returns.get(BENCHMARK_ETF)),
        }
        return closes, summary

    def get_earnings_window(
        self, ticker: str, event: EarningsEvent, sector_etf: Optional[str]
    ) -> Tuple[pd.DataFrame, Dict]:
        """Get daily candles from T-5 to T+10 trading days around the reaction session.

        Returns:
            Tuple of (window DataFrame with 'day_offset' and ETF/SPY closes, reaction metrics)
        """
        daily = self.get_daily_bars(ticker)
        reaction_pos = _reaction_position(daily.index, event)
        if reaction_pos is None:
            return pd.DataFrame(), {}

        start = max(reaction_pos - WINDOW_DAYS_BEFORE, 0)
        window = daily.iloc[start : reaction_pos + WINDOW_DAYS_AFTER + 1].copy()
        window.insert(0, "day_offset", range(start - reaction_pos, start - reaction_pos + len(window)))
        rows = slice(start, reaction_pos + WINDOW_DAYS_AFTER + 1)
        for days in MOVING_AVERAGE_WINDOWS:
            window[f"sma_{days}"] = daily["close"].rolling(days).mean().iloc[rows]
        window["high_52w"] = daily["high"].rolling(FIFTY_TWO_WEEK_SESSIONS).max().iloc[rows]
        window["low_52w"] = daily["low"].rolling(FIFTY_TWO_WEEK_SESSIONS).min().iloc[rows]
        for symbol in (sector_etf, BENCHMARK_ETF):
            if symbol and not self.get_daily_bars(symbol).empty:
                window[f"{symbol}_close"] = self.get_daily_bars(symbol)["close"].reindex(window.index)

        metrics = _reaction_metrics(window, sector_etf)
        metrics["reaction_date"] = _date_str(daily.index[reaction_pos])
        metrics["is_partial"] = len(window) < WINDOW_DAYS_BEFORE + WINDOW_DAYS_AFTER + 1
        return window, metrics

    def get_intraday_window(self, ticker: str, event: EarningsEvent) -> pd.DataFrame:
        """Get 5-min candles, including extended hours, from T-2 to T+2 trading days."""
        daily = self.get_daily_bars(ticker)
        reaction_pos = _reaction_position(daily.index, event)
        if reaction_pos is None:
            return pd.DataFrame()

        sessions = daily.index[
            max(reaction_pos - INTRADAY_DAYS_AROUND, 0) : reaction_pos + INTRADAY_DAYS_AROUND + 1
        ]
        start = datetime.combine(sessions[0].date(), EXTENDED_HOURS_START)
        end = datetime.combine(sessions[-1].date(), EXTENDED_HOURS_END)
        df = self.fetcher.get_intraday_bars(ticker, start, end, INTRADAY_INTERVAL_MINUTES)
        return df if df is not None else pd.DataFrame()

    def get_forecast_revision(self, ticker: str, event: EarningsEvent) -> Dict:
        """How consensus EPS estimates changed across a release, from yfinance's EPS trend.

        The trend holds estimates now and 7/30/60/90 days ago, so this only works for a release
        within the last 90 days and only when collecting as of today. 'before' is the latest
        snapshot taken before the release, 'after' the earliest one taken after it.
        """
        days_since = (date.today() - event.release_date).days
        if self.as_of != date.today():
            return {"available": False, "reason": "EPS trend is only available for today's collection"}
        before_ages = {col: age for col, age in EPS_TREND_SNAPSHOT_AGES.items() if age > days_since}
        if not before_ages:
            return {"available": False, "reason": f"release was {days_since} days ago; EPS trend covers 90 days"}

        trend = self.fetcher.get_eps_trend(ticker)
        if trend is None:
            return {"available": False, "reason": "no EPS trend data"}

        before_col = min(before_ages, key=before_ages.get)
        after_col = max(
            (col for col, age in EPS_TREND_SNAPSHOT_AGES.items() if age <= days_since),
            key=EPS_TREND_SNAPSHOT_AGES.get,
        )
        periods = []
        for period, label in EPS_TREND_PERIODS.items():
            if period not in trend.index:
                continue
            before, after, current = (
                _optional_float(trend.at[period, col]) for col in (before_col, after_col, "current")
            )
            periods.append(
                {
                    "period": period,
                    "label": label,
                    "before": before,
                    "after": after,
                    "current": current,
                    "change_pct": _estimate_change_pct(before, current),
                }
            )
        return {
            "available": True,
            "source": "yfinance eps_trend",
            "release_date": event.release_date.isoformat(),
            "before_snapshot": _snapshot_date(before_col),
            "after_snapshot": _snapshot_date(after_col),
            "periods": periods,
        }

    def collect(self, ticker: str, num_quarters: int = 4) -> Dict:
        """Collect all price context for a ticker and write it under <output_dir>/<TICKER>/<as_of>/.

        Returns:
            The manifest dict that is also written to manifest.json
        """
        ticker = ticker.upper()
        out_dir = self.output_dir / ticker / self.as_of.isoformat()
        out_dir.mkdir(parents=True, exist_ok=True)

        sector = (self.fetcher.get_company_info(ticker) or {}).get("sector") or None
        sector_etf = SECTOR_ETFS.get(sector)
        if sector_etf is None:
            logger.warning(f"No sector ETF mapping for {ticker} (sector={sector!r})")

        past_events, upcoming = self.resolve_earnings_events(ticker, num_quarters)

        daily = self.get_daily_history(ticker)
        _write_csv(daily, out_dir / "daily_90d.csv")

        sector_closes, sector_summary = self.get_sector_performance(ticker, sector_etf)
        _write_csv(sector_closes, out_dir / "sector_performance_63d.csv")

        earnings = []
        for event in past_events:
            event_dir = out_dir / "earnings" / event.release_date.isoformat()
            window, metrics = self.get_earnings_window(ticker, event, sector_etf)
            intraday = self.get_intraday_window(ticker, event)
            files = {
                "daily_window": _write_csv(window, event_dir / "daily_window.csv"),
                "intraday_5min": _write_csv(intraday, event_dir / "intraday_5min.csv"),
            }
            earnings.append(
                {
                    **_event_dict(event),
                    "metrics": metrics,
                    "intraday_bars": len(intraday),
                    "files": {k: str(v.relative_to(out_dir)) if v else None for k, v in files.items()},
                }
            )

        forecast_revision = self.get_forecast_revision(ticker, past_events[0]) if past_events else None

        manifest = {
            "ticker": ticker,
            "as_of": self.as_of.isoformat(),
            "collected_at": datetime.now().isoformat(timespec="seconds"),
            "sector": sector,
            "sector_etf": sector_etf,
            "benchmark_etf": BENCHMARK_ETF,
            "upcoming_earnings": _event_dict(upcoming) if upcoming else None,
            "daily_history": {"file": "daily_90d.csv", "rows": len(daily)},
            "sector_performance": {**sector_summary, "file": "sector_performance_63d.csv"},
            "earnings": earnings,
            "forecast_revision": forecast_revision,
        }
        (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, default=str))
        logger.info(f"Wrote earnings price context for {ticker} to {out_dir}")
        return manifest

    def _events_from_fmp(self, ticker: str) -> List[EarningsEvent]:
        df = self.fetcher.get_historical_earnings_calendar_fmp(ticker, limit=12)
        if df is None or df.empty:
            return []
        return [
            EarningsEvent(
                release_date=row["announceDate"].date(),
                timing=_normalize_timing(row.get("releaseTime")),
                fiscal_period_end=_optional_date(row.get("fiscalDateEnding")),
                eps_estimate=_optional_float(row.get("epsEstimate")),
                eps_actual=_optional_float(row.get("epsActual")),
                revenue_estimate=_optional_float(row.get("revenueEstimate")),
                revenue_actual=_optional_float(row.get("revenueActual")),
            )
            for _, row in df.iterrows()
        ]

    def _events_from_yfinance(self, ticker: str) -> List[EarningsEvent]:
        df = self.fetcher.get_earnings_dates(ticker, limit=12)
        if df is None or df.empty:
            return []
        if "Event Type" in df.columns:
            df = df[df["Event Type"] == "Earnings"]
        return [
            EarningsEvent(
                release_date=ts.date(),
                timing=_timing_from_timestamp(ts),
                eps_estimate=_optional_float(row.get("EPS Estimate")),
                eps_actual=_optional_float(row.get("Reported EPS")),
            )
            for ts, row in df.iterrows()
        ]


def _reaction_position(index: pd.DatetimeIndex, event: EarningsEvent) -> Optional[int]:
    """Index position of the first session that trades on the earnings news."""
    release_pos = int(index.searchsorted(pd.Timestamp(event.release_date)))
    if release_pos >= len(index):
        return None
    released_on_session = index[release_pos].date() == event.release_date
    if event.timing == "amc" and released_on_session:
        release_pos += 1
    return release_pos if release_pos < len(index) else None


def _reaction_metrics(window: pd.DataFrame, sector_etf: Optional[str]) -> Dict:
    by_offset = window.set_index("day_offset")
    if -1 not in by_offset.index or 0 not in by_offset.index:
        return {}

    def returns_for(column: str, prefix: str) -> Dict:
        if column not in by_offset.columns:
            return {}
        base = by_offset.at[-1, column]
        return {
            f"{prefix}_day0_return_pct": _pct_change(base, by_offset.at[0, column]),
            **{
                f"{prefix}_t{n}_return_pct": _pct_change(base, by_offset.at[n, column])
                if n in by_offset.index
                else None
                for n in (5, WINDOW_DAYS_AFTER)
            },
        }

    pre_volume = by_offset.loc[by_offset.index < 0, "volume"].mean()
    metrics = {
        "pre_earnings_close": _round(by_offset.at[-1, "close"]),
        "gap_pct": _pct_change(by_offset.at[-1, "close"], by_offset.at[0, "open"]),
        "day0_range_pct": _pct_change(by_offset.at[0, "low"], by_offset.at[0, "high"]),
        "day0_volume_ratio": _round(by_offset.at[0, "volume"] / pre_volume) if pre_volume else None,
        **returns_for("close", "stock"),
        **returns_for(f"{sector_etf}_close", "sector"),
        **returns_for(f"{BENCHMARK_ETF}_close", "market"),
    }
    metrics["abnormal_day0_vs_sector_pct"] = _diff(
        metrics.get("stock_day0_return_pct"), metrics.get("sector_day0_return_pct")
    )
    return metrics


def _estimate_change_pct(before: Optional[float], after: Optional[float]) -> Optional[float]:
    """Change relative to the size of the old estimate, so a smaller expected loss is an increase."""
    if before is None or after is None or before == 0:
        return None
    return _round((after - before) / abs(before) * 100)


def _snapshot_date(column: str) -> str:
    return (date.today() - timedelta(days=EPS_TREND_SNAPSHOT_AGES[column])).isoformat()


def _normalize_timing(value) -> str:
    value = str(value or "").strip().lower()
    return value if value in ("bmo", "amc") else "unknown"


def _timing_from_timestamp(ts: pd.Timestamp) -> str:
    if ts.time() == time(0, 0):
        return "unknown"
    if ts.time() < MARKET_OPEN:
        return "bmo"
    if ts.time() >= MARKET_CLOSE:
        return "amc"
    return "unknown"


def _event_dict(event: EarningsEvent) -> Dict:
    return {k: v.isoformat() if isinstance(v, date) else v for k, v in asdict(event).items()}


def _write_csv(df: pd.DataFrame, path: Path) -> Optional[Path]:
    if df is None or df.empty:
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    df.round(4).to_csv(path)
    return path


def _pct_change(start, end) -> Optional[float]:
    if start is None or end is None or pd.isna(start) or pd.isna(end) or start == 0:
        return None
    return _round((end / start - 1) * 100)


def _diff(a: Optional[float], b: Optional[float]) -> Optional[float]:
    if a is None or b is None:
        return None
    return _round(a - b)


def _round(value, digits: int = 4) -> Optional[float]:
    if value is None or pd.isna(value):
        return None
    return round(float(value), digits)


def _optional_float(value) -> Optional[float]:
    return None if value is None or pd.isna(value) else float(value)


def _optional_date(value) -> Optional[date]:
    return None if value is None or pd.isna(value) else pd.Timestamp(value).date()


def _date_str(value) -> str:
    return pd.Timestamp(value).date().isoformat()


def _read_tickers(tickers: List[str], tickers_file: Optional[str]) -> List[str]:
    if tickers_file:
        lines = Path(tickers_file).read_text().splitlines()
        tickers = tickers + [t.strip() for t in lines if t.strip() and not t.startswith("#")]
    return list(dict.fromkeys(t.upper() for t in tickers))


def main():
    """Command-line entry point."""
    parser = argparse.ArgumentParser(description="Collect price data around earnings releases")
    parser.add_argument("tickers", nargs="*", help="Ticker symbols, e.g. AAPL MSFT")
    parser.add_argument("--tickers-file", help="File with one ticker per line")
    parser.add_argument("--quarters", type=int, default=4, help="Number of past releases (default: 4)")
    parser.add_argument("--as-of", type=date.fromisoformat, help="Collection date, YYYY-MM-DD (default: today)")
    parser.add_argument("--output-dir", help="Output root (default: <DATA_DIR>/earnings_price_context)")
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    tickers = _read_tickers(args.tickers, args.tickers_file)
    if not tickers:
        parser.error("provide at least one ticker or --tickers-file")

    collector = EarningsPriceContextCollector(output_dir=args.output_dir, as_of=args.as_of)
    failures = []
    for ticker in tickers:
        try:
            manifest = collector.collect(ticker, args.quarters)
            print(f"{ticker}: {len(manifest['earnings'])} releases -> {collector.output_dir / ticker / collector.as_of.isoformat()}")
        except Exception as e:
            logger.exception(f"Failed to collect earnings price context for {ticker}")
            failures.append((ticker, str(e)))

    if failures:
        print(f"Failed: {', '.join(t for t, _ in failures)}")


if __name__ == "__main__":
    main()
