#!/usr/bin/env python3
"""
Export the local earning.yaml data store (collected by quarterly_annual_collector.py)
to Google Sheets: one row per ticker, one column per period.

This is a separate export path from run_earnings_to_sheets.py, which uploads the
current-quarter-focused CSV from generate_earnings_analysis.py instead.

Column layout is driven by whatever header row already exists in the target
tab (see sheet_column_mapping.py): each header cell is parsed into a resolver,
so a tab's column names/order/typos are matched exactly rather than
hardcoded here. If the target tab is empty, a generic wide layout is written
instead (see earning_store_export.py) to bootstrap a brand new tab.

When the tab already has data, each ticker's row is updated in place if it's
already present (matched by the ticker column), and only genuinely new
tickers are appended — this avoids creating duplicate rows on reruns.

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
from sheet_column_mapping import build_rows_for_headers
from run_earnings_to_sheets import upload_csv_to_sheets, get_existing_header, create_sheets_client

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


def build_headers_and_rows(client, spreadsheet_id, tab_name, ordered_keys, ticker_data):
    """
    Build the CSV header + rows for this export, matching whatever header
    already exists in the target tab if there is one, or falling back to a
    generic wide layout to bootstrap a brand new tab.

    Returns:
        (headers, rows, matched_existing_header: bool)
    """
    existing_header = get_existing_header(client, spreadsheet_id, tab_name)

    if existing_header:
        logger.info(f"Tab '{tab_name}' already has a header, mapping data to its columns...")
        rows, unrecognized = build_rows_for_headers(existing_header, ordered_keys, ticker_data)
        if unrecognized:
            logger.warning(
                f"{len(unrecognized)} column(s) in '{tab_name}' were not recognized and will "
                f"be left blank: {unrecognized}"
            )
        return existing_header, rows, True

    logger.info(f"Tab '{tab_name}' is empty, writing a new generic wide-format header...")
    headers, rows = build_export_rows(ordered_keys, ticker_data)
    return headers, rows, False


def _column_letter(column_number: int) -> str:
    """Convert a 1-indexed column number to its spreadsheet letter(s), e.g. 1 -> 'A', 28 -> 'AB'."""
    letters = ""
    while column_number > 0:
        column_number, remainder = divmod(column_number - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


def get_ticker_row_numbers(client, spreadsheet_id, tab_name, ticker_col="A", start_row=2):
    """
    Map each ticker already present in a sheet tab to its row number.

    Returns:
        {ticker (uppercase): row_number (1-indexed)}
    """
    result = (
        client.service.spreadsheets()
        .values()
        .get(spreadsheetId=spreadsheet_id, range=f"{tab_name}!{ticker_col}{start_row}:{ticker_col}")
        .execute()
    )
    values = result.get("values", [])
    return {
        row[0].strip().upper(): start_row + i
        for i, row in enumerate(values)
        if row and row[0].strip()
    }


def get_next_available_row(client, spreadsheet_id, tab_name, ticker_col="A") -> int:
    """
    Return the row number immediately after the last row with any data in
    ticker_col (including the header). Computed explicitly from the actual
    column contents rather than relying on the Sheets API's own append/
    "find the table" heuristics, which have been observed to misplace rows
    (see upsert_rows).
    """
    result = (
        client.service.spreadsheets()
        .values()
        .get(spreadsheetId=spreadsheet_id, range=f"{tab_name}!{ticker_col}:{ticker_col}")
        .execute()
    )
    return len(result.get("values", [])) + 1


def upsert_rows(client, spreadsheet_id, tab_name, headers, ordered_keys, rows):
    """
    Write each ticker's row into an existing tab: update its row in place if
    the ticker is already present (matched by column A), otherwise write it
    to an explicitly computed new row. Prevents duplicate ticker rows from
    accumulating on reruns.

    New rows are written with an explicit range via values().update() rather
    than values().append(), since append()'s "find the existing table"
    heuristic has been observed to insert rows in the wrong place (e.g.
    pushing an existing header row down) when a sheet's structure doesn't
    match what it expects.
    """
    client.get_or_create_sheet_tab(spreadsheet_id, tab_name)
    existing_rows = get_ticker_row_numbers(client, spreadsheet_id, tab_name)
    last_col = _column_letter(len(headers))

    to_append = []
    updated_count = 0

    for (_, ticker), row in zip(ordered_keys, rows):
        row_number = existing_rows.get(ticker.upper())
        if row_number:
            client.service.spreadsheets().values().update(
                spreadsheetId=spreadsheet_id,
                range=f"{tab_name}!A{row_number}:{last_col}{row_number}",
                valueInputOption="USER_ENTERED",
                body={"values": [row]},
            ).execute()
            updated_count += 1
        else:
            to_append.append(row)

    if to_append:
        start_row = get_next_available_row(client, spreadsheet_id, tab_name)
        end_row = start_row + len(to_append) - 1
        client.service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=f"{tab_name}!A{start_row}:{last_col}{end_row}",
            valueInputOption="USER_ENTERED",
            body={"values": to_append},
        ).execute()

    logger.info(
        f"Updated {updated_count} existing row(s), appended {len(to_append)} new row(s) in '{tab_name}'"
    )


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

    client = create_sheets_client()
    headers, rows, matched_existing_header = build_headers_and_rows(
        client, args.spreadsheet_id, args.tab_name, ordered_keys, ticker_data
    )

    with open(args.output, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)

    logger.info(f"Wrote {len(rows)} rows to {args.output}")

    if not args.skip_upload:
        if matched_existing_header:
            upsert_rows(client, args.spreadsheet_id, args.tab_name, headers, ordered_keys, rows)
        else:
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
