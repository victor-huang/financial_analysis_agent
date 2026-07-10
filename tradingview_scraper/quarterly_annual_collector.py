#!/usr/bin/env python3
"""
Collect quarterly and yearly Revenue/EPS data (historical + forecast) from
TradingView's forecast page for a list of tickers.

TradingView's free tier caps historical depth (typically ~7-8 quarters and
~5 years), and the exact count can vary by ticker. This script pulls as many
data points as the page exposes and reports how many were found, using each
company's own fiscal reporting quarter/year (not the calendar quarter).

Usage:
    python quarterly_annual_collector.py --tickers "LLY, AAPL, MSFT"
    python quarterly_annual_collector.py --tickers-file tickers.txt
    python quarterly_annual_collector.py --tickers LLY --no-headless
    python quarterly_annual_collector.py --tickers "LLY, AAPL, MSFT" --concurrency 3
"""

import argparse
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional, Tuple

import requests

from tradingview_final_scraper import TradingViewFinalScraper
from earnings_data_store import (
    load_existing_data,
    save_data,
    merge_ticker_data,
    prompt_confirm_overwrite,
)

SYMBOL_SEARCH_URL = "https://symbol-search.tradingview.com/symbol_search/v3/"
PREFERRED_EXCHANGES = ("NYSE", "NASDAQ", "AMEX")


def resolve_exchange(ticker: str) -> Optional[str]:
    """
    Resolve which exchange a ticker's primary US listing trades on.

    TradingView's forecast page 404s if the wrong exchange is used in the
    URL (it does not auto-redirect), so we look the ticker up via
    TradingView's own symbol search first.

    Args:
        ticker: Stock ticker symbol

    Returns:
        Exchange name (e.g. "NYSE") or None if not found
    """
    params = {
        "text": ticker,
        "hl": "1",
        "exchange": "",
        "lang": "en",
        "search_type": "stocks",
        "domain": "production",
        "sort_by_country": "US",
    }
    headers = {
        "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "origin": "https://www.tradingview.com",
        "referer": "https://www.tradingview.com/",
    }

    response = requests.get(SYMBOL_SEARCH_URL, params=params, headers=headers, timeout=15)
    response.raise_for_status()
    symbols = response.json().get("symbols", [])

    candidates = [
        s
        for s in symbols
        if re.sub(r"</?em>", "", s.get("symbol", "")).upper() == ticker.upper()
        and s.get("country") == "US"
    ]

    if not candidates:
        return None

    for exchange in PREFERRED_EXCHANGES:
        for candidate in candidates:
            if candidate.get("exchange") == exchange:
                return exchange

    return candidates[0].get("exchange")


def _format_period_label(period: str) -> str:
    """
    Convert a raw TradingView period label to the requested display format.

    "Q3 '24" -> "Q3 2024" (company's own fiscal quarter, not calendar quarter)
    "2024"   -> "2024 Yearly"
    """
    quarterly_match = re.match(r"Q(\d)\s*'(\d{2})$", period)
    if quarterly_match:
        quarter, year_suffix = quarterly_match.group(1), int(quarterly_match.group(2))
        year = 2000 + year_suffix if year_suffix < 50 else 1900 + year_suffix
        return f"Q{quarter} {year}"

    if re.match(r"^\d{4}$", period):
        return f"{period} Yearly"

    return period


def _extract_points(items: List[Dict], value_key: str) -> Dict[str, float]:
    """Build an ordered {label: value} dict from a list of period data points."""
    points = {}
    for item in items:
        value = item.get(value_key)
        if value is not None:
            points[_format_period_label(item["period"])] = value
    return points


def transform_financial_data(raw_data: Dict) -> Dict:
    """
    Reshape the scraper's raw annual/quarterly EPS+Revenue payload into the
    metric-first structure used for reporting: {metric: {bucket: {label: value}}}.

    Args:
        raw_data: Output of TradingViewFinalScraper.fetch_all_financial_data

    Returns:
        {
            "revenue": {"quarterly": {...}, "annual": {...},
                        "quarterly_forecast": {...}, "annual_forecast": {...}},
            "eps": {...same shape...},
        }
    """
    result = {
        "currency": raw_data.get("currency"),
        "company_name": raw_data.get("company_name"),
        "sector": raw_data.get("sector"),
        "market_cap_billions": raw_data.get("market_cap_billions"),
    }
    for metric in ("revenue", "eps"):
        quarterly = raw_data.get("quarterly", {}).get(metric, {})
        annual = raw_data.get("annual", {}).get(metric, {})
        result[metric] = {
            "quarterly": _extract_points(quarterly.get("historical", []), "reported"),
            "annual": _extract_points(annual.get("historical", []), "reported"),
            "quarterly_forecast": _extract_points(quarterly.get("forecast", []), "estimate"),
            "annual_forecast": _extract_points(annual.get("forecast", []), "estimate"),
        }
    return result


BUCKET_LABELS = {
    "quarterly": "quarterly historical",
    "annual": "annual historical",
    "quarterly_forecast": "quarterly forecast",
    "annual_forecast": "annual forecast",
}


def find_missing_data(ticker: str, transformed: Dict) -> List[str]:
    """
    Identify which metric/bucket combinations came back empty.

    Returns:
        List of human-readable log messages (empty if nothing is missing)
    """
    messages = []
    for field in ("currency", "company_name", "sector", "market_cap_billions"):
        if transformed.get(field) is None:
            messages.append(f"{ticker}: missing {field} data")
    for metric in ("revenue", "eps"):
        for bucket, label in BUCKET_LABELS.items():
            if not transformed.get(metric, {}).get(bucket):
                messages.append(f"{ticker}: missing {metric} {label} data")
    return messages


def _format_points_line(points: Dict[str, float]) -> str:
    if not points:
        return "(none)"
    return ", ".join(f"{label}: {value}" for label, value in points.items())


def print_ticker_report(ticker: str, transformed: Dict) -> None:
    """Print the per-ticker data summary in the requested review format."""
    currency = transformed.get("currency") or "unknown currency"
    company_name = transformed.get("company_name") or "unknown"
    sector = transformed.get("sector") or "unknown"
    market_cap = transformed.get("market_cap_billions")
    market_cap_display = f"{market_cap:.2f}" if market_cap is not None else "unknown"

    print(f"\nTicker: {ticker}")
    print(f"Company name: {company_name}")
    print(f"Market segment: {sector}")
    print(f"Market Cap (B): {market_cap_display}")
    print(f"Currency: {currency}")

    print(f"\nRevenue (in millions {currency}):")
    print(f"Quaterly data: {_format_points_line(transformed['revenue']['quarterly'])}")
    print(f"Yearly Data: {_format_points_line(transformed['revenue']['annual'])}")
    print(f"\nForecast Quaterly: {_format_points_line(transformed['revenue']['quarterly_forecast'])}")
    print(f"Forcast Yeasly: {_format_points_line(transformed['revenue']['annual_forecast'])}")

    print(f"\nEPS (per share, {currency}):")
    print(f"Quaterly Data: {_format_points_line(transformed['eps']['quarterly'])}")
    print(f"Yearly Data: {_format_points_line(transformed['eps']['annual'])}")
    print(f"\nForecast Quaterly: {_format_points_line(transformed['eps']['quarterly_forecast'])}")
    print(f"Forcast Yeasly: {_format_points_line(transformed['eps']['annual_forecast'])}")


def _process_ticker(
    ticker: str, headless: bool, confirm_overwrite
) -> Tuple[str, Optional[Dict], List[str], List[str]]:
    """
    Scrape, merge into the on-disk store, and print the report for a single ticker.

    Runs standalone (no shared mutable state) so it's safe to call from
    multiple threads concurrently.

    Returns:
        (ticker, merged_data_or_None, merge_log, missing_log)
    """
    ticker = ticker.strip().upper()

    exchange = resolve_exchange(ticker)
    if not exchange:
        print(f"\nTicker: {ticker}")
        print("  ✗ Could not resolve exchange for this ticker, skipping")
        return ticker, None, [], [f"{ticker}: could not resolve exchange"]

    scraper = TradingViewFinalScraper(headless=headless)
    raw_data = scraper.fetch_all_financial_data(ticker, exchange)

    if not raw_data:
        print(f"\nTicker: {ticker}")
        print(f"  ✗ No forecast page data available ({exchange}:{ticker})")
        return ticker, None, [], [f"{ticker}: no forecast page data available"]

    transformed = transform_financial_data(raw_data)

    existing = load_existing_data(exchange, ticker)
    merged, merge_log = merge_ticker_data(ticker, existing, transformed, confirm_overwrite)
    saved_path = save_data(exchange, ticker, merged)

    print_ticker_report(ticker, merged)
    print(f"Saved to: {saved_path}")

    return ticker, merged, merge_log, find_missing_data(ticker, merged)


def collect_for_tickers(
    tickers: List[str],
    headless: bool = True,
    confirm_overwrite=prompt_confirm_overwrite,
    concurrency: int = 1,
) -> Dict[str, Dict]:
    """
    Fetch, merge into the on-disk store, and report Revenue/EPS data for each ticker.

    Data is persisted to ./company_earnings_data/<exchange>_<ticker>/earning.yaml and
    extended (not replaced) on each run: new reported data points are added, conflicting
    reported values go through confirm_overwrite, and forecast values are always
    refreshed automatically.

    Args:
        tickers: List of ticker symbols
        headless: Run the scraping browser in headless mode
        confirm_overwrite: Callable(ticker, metric, bucket, period, old_value, new_value) -> bool,
            used when a freshly scraped reported value conflicts with a stored one
        concurrency: Number of tickers to scrape in parallel (default: 1, sequential).
            Each ticker writes to its own file, so concurrent runs don't conflict.
            Note that scraping logs from concurrent tickers can interleave in the
            console output; the per-ticker report itself is still printed as a
            single block once that ticker finishes.

    Returns:
        {ticker: merged_data} for tickers that returned data
    """
    clean_tickers = [t.strip().upper() for t in tickers if t.strip()]

    results = {}
    all_missing_messages = []
    all_merge_messages = []

    def _record(ticker, merged, merge_log, missing_log):
        if merged is not None:
            results[ticker] = merged
        all_merge_messages.extend(merge_log)
        all_missing_messages.extend(missing_log)

    if concurrency <= 1:
        for ticker in clean_tickers:
            _record(*_process_ticker(ticker, headless, confirm_overwrite))
    else:
        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            futures = {
                executor.submit(_process_ticker, ticker, headless, confirm_overwrite): ticker
                for ticker in clean_tickers
            }
            for future in as_completed(futures):
                ticker = futures[future]
                try:
                    _record(*future.result())
                except Exception as e:
                    print(f"\nTicker: {ticker}")
                    print(f"  ✗ Error: {e}")
                    all_missing_messages.append(f"{ticker}: error during scraping ({e})")

    if all_merge_messages:
        print(f"\n{'='*80}")
        print("Data Store Merge Log")
        print("=" * 80)
        for message in all_merge_messages:
            print(f"  - {message}")

    if all_missing_messages:
        print(f"\n{'='*80}")
        print("Missing Data Log")
        print("=" * 80)
        for message in all_missing_messages:
            print(f"  - {message}")

    return results


def _parse_tickers_arg(args: argparse.Namespace) -> List[str]:
    if args.tickers_file:
        with open(args.tickers_file, "r", encoding="utf-8") as f:
            content = f.read()
        return [t.strip() for t in re.split(r"[,\n]", content) if t.strip()]

    return [t.strip() for t in args.tickers.split(",") if t.strip()]


def main():
    parser = argparse.ArgumentParser(
        description="Collect quarterly/yearly Revenue and EPS data (historical + forecast) from TradingView"
    )
    parser.add_argument(
        "--tickers",
        "-t",
        type=str,
        default=None,
        help='Comma-separated list of tickers (e.g., "LLY, AAPL, MSFT")',
    )
    parser.add_argument(
        "--tickers-file",
        type=str,
        default=None,
        help="Path to a file with tickers (comma-separated or one per line)",
    )
    parser.add_argument(
        "--no-headless",
        action="store_true",
        help="Show browser during scraping (for debugging)",
    )
    parser.add_argument(
        "--on-reported-conflict",
        choices=["ask", "overwrite", "keep"],
        default="ask",
        help="How to resolve a conflicting reported data point already in the store: "
        "'ask' (default, prompt interactively), 'overwrite' (always take the new "
        "scraped value), 'keep' (always keep the stored value). Forecast values are "
        "always overwritten regardless of this setting.",
    )
    parser.add_argument(
        "--concurrency",
        "-c",
        type=int,
        default=1,
        help="Number of tickers to scrape in parallel (default: 1, sequential). "
        "Requires --on-reported-conflict overwrite|keep, since concurrent "
        "interactive prompts can't be resolved safely.",
    )

    args = parser.parse_args()

    if not args.tickers and not args.tickers_file:
        parser.error("Provide --tickers or --tickers-file")

    if args.concurrency > 1 and args.on_reported_conflict == "ask":
        parser.error(
            "--concurrency > 1 requires --on-reported-conflict overwrite|keep "
            "(interactive prompts from multiple tickers at once can't be resolved safely)"
        )

    tickers = _parse_tickers_arg(args)

    if args.on_reported_conflict == "overwrite":
        confirm_overwrite = lambda *a, **kw: True
    elif args.on_reported_conflict == "keep":
        confirm_overwrite = lambda *a, **kw: False
    else:
        confirm_overwrite = prompt_confirm_overwrite

    collect_for_tickers(
        tickers,
        headless=not args.no_headless,
        confirm_overwrite=confirm_overwrite,
        concurrency=args.concurrency,
    )


if __name__ == "__main__":
    main()
