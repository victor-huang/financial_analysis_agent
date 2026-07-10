#!/usr/bin/env python3
"""
Export the local earning.yaml data store (collected by quarterly_annual_collector.py)
to Google Sheets in a wide format: one row per ticker, one column per period.

This is a separate export path from run_earnings_to_sheets.py, which uploads the
current-quarter-focused CSV from generate_earnings_analysis.py instead. Column
names here intentionally differ (e.g. "Company Name" / "Market Segment" instead
of "Company name" / "Market segment") since they come from a different pipeline.

By default this exports whatever is already saved on disk under
company_earnings_data/. Pass --refresh to re-scrape and merge each ticker first.

Usage:
    python export_earning_store_to_sheets.py --tickers "LLY, AAPL" --spreadsheet-id <ID>
    python export_earning_store_to_sheets.py --tickers-file tickers.txt --spreadsheet-id <ID> --refresh
    python export_earning_store_to_sheets.py --tickers LLY --spreadsheet-id <ID> --skip-upload
"""

import argparse
import csv
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))

from quarterly_annual_collector import resolve_exchange, collect_for_tickers, _parse_tickers_arg
from earnings_data_store import load_existing_data, prompt_confirm_overwrite
from earning_store_export import build_export_rows
from run_earnings_to_sheets import upload_csv_to_sheets

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def gather_ticker_data(tickers, refresh, headless, confirm_overwrite):
    """
    Resolve each ticker's exchange and load its stored earning.yaml data,
    optionally re-scraping and merging first.

    Args:
        tickers: List of ticker symbols
        refresh: If True, run the collector (scrape + merge + save) before loading
        headless: Run the scraping browser in headless mode (only used if refresh)
        confirm_overwrite: Conflict resolver passed through to the collector (only used if refresh)

    Returns:
        (ordered_keys, ticker_data) where ordered_keys is an ordered list of
        (exchange, ticker) tuples and ticker_data maps each key to its stored dict
    """
    if refresh:
        collect_for_tickers(tickers, headless=headless, confirm_overwrite=confirm_overwrite)

    ordered_keys = []
    ticker_data = {}

    for ticker in tickers:
        ticker = ticker.strip().upper()
        if not ticker:
            continue

        exchange = resolve_exchange(ticker)
        if not exchange:
            logger.warning(f"Could not resolve exchange for {ticker}, skipping")
            continue

        data = load_existing_data(exchange, ticker)
        has_any_data = any(data.get(metric, {}).values() for metric in ("revenue", "eps"))
        if not has_any_data:
            logger.warning(
                f"No stored data found for {exchange}:{ticker} — "
                f"run quarterly_annual_collector.py first, or pass --refresh"
            )

        key = (exchange, ticker)
        ordered_keys.append(key)
        ticker_data[key] = data

    return ordered_keys, ticker_data


def main():
    parser = argparse.ArgumentParser(
        description="Export the earning.yaml data store to Google Sheets (wide format: one row per ticker)"
    )
    parser.add_argument(
        "--tickers", "-t", type=str, default=None,
        help='Comma-separated list of tickers (e.g., "LLY, AAPL")',
    )
    parser.add_argument(
        "--tickers-file", type=str, default=None,
        help="Path to a file with tickers (comma-separated or one per line)",
    )
    parser.add_argument(
        "--spreadsheet-id", required=True, help="Google Sheets spreadsheet ID (from the URL)"
    )
    parser.add_argument(
        "--tab-name", default="Earnings_Store",
        help="Name of the tab to write to (default: Earnings_Store)",
    )
    parser.add_argument(
        "--output", "-o", default="earning_store_export.csv", help="Local CSV filename"
    )
    parser.add_argument(
        "--no-clear", action="store_true",
        help="Do not clear existing data before writing (append mode)",
    )
    parser.add_argument("--no-format", action="store_true", help="Do not format the header row")
    parser.add_argument(
        "--keep-csv", action="store_true", help="Keep the local CSV file after uploading"
    )
    parser.add_argument(
        "--skip-upload", action="store_true", help="Generate CSV only, do not upload"
    )
    parser.add_argument(
        "--refresh", action="store_true",
        help="Re-scrape TradingView and merge into the store before exporting "
        "(default: export the store as-is)",
    )
    parser.add_argument(
        "--no-headless", action="store_true",
        help="Show browser during scraping (only relevant with --refresh)",
    )
    parser.add_argument(
        "--on-reported-conflict", choices=["ask", "overwrite", "keep"], default="ask",
        help="How to resolve conflicting reported data during --refresh "
        "(see quarterly_annual_collector.py)",
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose logging")

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    if not args.tickers and not args.tickers_file:
        parser.error("Provide --tickers or --tickers-file")

    tickers = _parse_tickers_arg(args)

    if args.on_reported_conflict == "overwrite":
        confirm_overwrite = lambda *a, **kw: True
    elif args.on_reported_conflict == "keep":
        confirm_overwrite = lambda *a, **kw: False
    else:
        confirm_overwrite = prompt_confirm_overwrite

    ordered_keys, ticker_data = gather_ticker_data(
        tickers, refresh=args.refresh, headless=not args.no_headless, confirm_overwrite=confirm_overwrite
    )

    if not ordered_keys:
        logger.warning("No tickers resolved, nothing to export")
        return

    headers, rows = build_export_rows(ordered_keys, ticker_data)

    with open(args.output, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)

    logger.info(f"Wrote {len(rows)} rows to {args.output}")

    if not args.skip_upload:
        upload_csv_to_sheets(
            csv_file=args.output,
            spreadsheet_id=args.spreadsheet_id,
            tab_name=args.tab_name,
            clear_existing=not args.no_clear,
            format_header=not args.no_format,
        )

    if not args.keep_csv and not args.skip_upload:
        Path(args.output).unlink()
        logger.info(f"Cleaned up local CSV file: {args.output}")


if __name__ == "__main__":
    main()
