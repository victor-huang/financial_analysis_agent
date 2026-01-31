#!/usr/bin/env python3
"""
Run earnings analysis and upload results to Google Sheets.

This script combines generate_earnings_analysis.py with Google Sheets upload,
providing a single command to generate earnings data and append it to a spreadsheet.

Usage:
    python run_earnings_to_sheets.py --tickers "AAPL,MSFT" --spreadsheet-id <ID> --tab-name "Earnings"
    python run_earnings_to_sheets.py --date 2025-01-15 --spreadsheet-id <ID> --tab-name "Jan15"
"""

import argparse
import csv
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

# Add parent directory to path to import financial_analysis_agent
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Load .env files from project root before importing config
from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env")
load_dotenv(PROJECT_ROOT / ".env.local", override=True)

from financial_analysis_agent.config import get_config
from financial_analysis_agent.export import GoogleSheetsClient

from generate_earnings_analysis import generate_earnings_analysis, parse_date

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def create_sheets_client() -> GoogleSheetsClient:
    """Create and return a GoogleSheetsClient using credentials from config."""
    config = get_config()

    credentials_path = config.get("apis.google_sheets.credentials_path")
    credentials_json_str = config.get("apis.google_sheets.credentials_json")

    if credentials_path and Path(credentials_path).exists():
        logger.info(f"Using credentials from file: {credentials_path}")
        return GoogleSheetsClient(credentials_path=credentials_path)
    elif credentials_json_str:
        logger.info("Using credentials from environment variable")
        credentials_json = json.loads(credentials_json_str)
        return GoogleSheetsClient(service_account_info=credentials_json)
    else:
        raise ValueError(
            "Google Sheets credentials not configured. "
            "Please set GOOGLE_SHEETS_CREDENTIALS_PATH or "
            "GOOGLE_SHEETS_CREDENTIALS_JSON in your .env file"
        )


def get_existing_header(client: GoogleSheetsClient, spreadsheet_id: str, tab_name: str):
    """
    Get the existing header row from a sheet tab if it exists.

    Returns:
        List of header values, or None if tab is empty or doesn't exist
    """
    try:
        result = (
            client.service.spreadsheets()
            .values()
            .get(spreadsheetId=spreadsheet_id, range=f"{tab_name}!A1:ZZ1")
            .execute()
        )
        values = result.get("values", [])
        if values and values[0]:
            return values[0]
        return None
    except Exception:
        return None


def get_existing_tickers_from_sheet(
    client: GoogleSheetsClient,
    spreadsheet_id: str,
    tab_name: str,
    ticker_col: str,
    start_row: int = 2,
) -> set:
    """
    Read existing ticker symbols from a column in Google Sheets.

    Args:
        client: GoogleSheetsClient instance
        spreadsheet_id: Google Sheets spreadsheet ID
        tab_name: Name of the tab to read from
        ticker_col: Column letter containing ticker symbols (e.g., 'A')
        start_row: Starting row number (1-indexed), default 2 to skip header

    Returns:
        Set of ticker symbols (uppercase) already in the sheet
    """
    try:
        range_notation = f"{tab_name}!{ticker_col}{start_row}:{ticker_col}"
        result = (
            client.service.spreadsheets()
            .values()
            .get(spreadsheetId=spreadsheet_id, range=range_notation)
            .execute()
        )
        values = result.get("values", [])
        tickers = {row[0].strip().upper() for row in values if row and row[0].strip()}
        logger.info(f"Found {len(tickers)} existing tickers in column {ticker_col}")
        return tickers
    except Exception as e:
        logger.warning(f"Could not read existing tickers from sheet: {e}")
        return set()


def upload_csv_to_sheets(
    csv_file: str,
    spreadsheet_id: str,
    tab_name: str,
    clear_existing: bool = True,
    format_header: bool = True,
) -> None:
    """
    Upload a CSV file to Google Sheets.

    If the tab already has data with the same header row, appends only the data rows.
    Otherwise, writes all data including the header.

    Args:
        csv_file: Path to CSV file
        spreadsheet_id: Google Sheets spreadsheet ID
        tab_name: Name of the tab to write to
        clear_existing: Whether to clear existing data (ignored if headers match)
        format_header: Whether to format the header row
    """
    logger.info("Initializing Google Sheets client...")
    client = create_sheets_client()

    # Read CSV file
    csv_path = Path(csv_file)
    with open(csv_path, "r", encoding="utf-8") as f:
        csv_reader = csv.reader(f)
        data = list(csv_reader)

    if not data:
        logger.warning(f"CSV file {csv_file} is empty")
        return

    csv_header = data[0]
    data_rows = data[1:]

    # Ensure tab exists
    client.get_or_create_sheet_tab(spreadsheet_id, tab_name)

    # Check if existing header matches
    existing_header = get_existing_header(client, spreadsheet_id, tab_name)

    if existing_header and existing_header == csv_header:
        # Headers match - append data rows only
        logger.info(
            f"Tab '{tab_name}' has matching headers, appending {len(data_rows)} data rows..."
        )
        result = client.append_data_to_sheet(
            spreadsheet_id=spreadsheet_id,
            data=data_rows,
            tab_name=tab_name,
        )
        updated_cells = result.get("updates", {}).get("updatedCells", 0)
        logger.info(f"Successfully appended {len(data_rows)} rows to Google Sheets!")
    else:
        # No existing data or different headers - write all data
        if existing_header:
            logger.info(f"Tab '{tab_name}' has different headers, replacing data...")
        else:
            logger.info(f"Tab '{tab_name}' is empty, writing all data...")

        result = client.write_csv_to_sheet(
            spreadsheet_id=spreadsheet_id,
            csv_file=csv_file,
            tab_name=tab_name,
            clear_existing=clear_existing,
        )

        if format_header:
            logger.info("Formatting header row...")
            client.format_header_row(
                spreadsheet_id=spreadsheet_id,
                tab_name=tab_name,
                bold=True,
                background_color={"red": 0.9, "green": 0.9, "blue": 0.9},
            )
        updated_cells = result.get("updatedCells", "N/A")
        logger.info(f"Successfully wrote {len(data)} rows to Google Sheets!")

    logger.info(
        f"  Spreadsheet: https://docs.google.com/spreadsheets/d/{spreadsheet_id}"
    )
    logger.info(f"  Tab: {tab_name}")


def main():
    """Main execution function."""
    parser = argparse.ArgumentParser(
        description="Generate earnings analysis and upload to Google Sheets",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate today's earnings and upload to Google Sheets
  python run_earnings_to_sheets.py \\
    --spreadsheet-id 1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms \\
    --tab-name "Earnings_Today"

  # Generate for specific tickers and upload
  python run_earnings_to_sheets.py \\
    --tickers "AAPL, MSFT, GOOGL" \\
    --spreadsheet-id 1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms \\
    --tab-name "Tech_Earnings"

  # Generate for specific date with custom concurrency
  python run_earnings_to_sheets.py \\
    --date 2025-01-15 \\
    --concurrency 5 \\
    --spreadsheet-id 1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms \\
    --tab-name "Jan15_Earnings"

  # Use reported quarter mode
  python run_earnings_to_sheets.py \\
    --tickers "NUE, RYAAY" \\
    --quarter-mode reported \\
    --spreadsheet-id 1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms \\
    --tab-name "Reported"

  # Keep local CSV file after upload
  python run_earnings_to_sheets.py \\
    --tickers "AAPL, MSFT" \\
    --output my_earnings.csv \\
    --keep-csv \\
    --spreadsheet-id 1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms \\
    --tab-name "Earnings"

  # Append to existing data (don't clear tab first)
  python run_earnings_to_sheets.py \\
    --tickers "AAPL, MSFT" \\
    --no-clear \\
    --spreadsheet-id 1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms \\
    --tab-name "Combined_Earnings"

  # Use tickers from a file (generated by update_extended_hours_prices.py)
  python run_earnings_to_sheets.py \\
    --tickers-file tickers_from_spreadsheet.txt \\
    --spreadsheet-id 1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms \\
    --tab-name "Earnings"

  # Only process new tickers (skip ones already in spreadsheet column A)
  python run_earnings_to_sheets.py \\
    --tickers-file tickers_from_spreadsheet.txt \\
    --spreadsheet-id 1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms \\
    --tab-name "Earnings_Data" \\
    --skip-existing-tickers-col A
        """,
    )

    # Earnings analysis arguments (from generate_earnings_analysis.py)
    parser.add_argument(
        "--date",
        type=parse_date,
        default=datetime.now(),
        help="Date to fetch earnings for (YYYY-MM-DD). Default: today",
    )

    parser.add_argument(
        "--output",
        "-o",
        default=None,
        help="Output CSV filename. Default: earnings_analysis_YYYY-MM-DD.csv",
    )

    parser.add_argument(
        "--limit",
        "-l",
        type=int,
        default=None,
        help="Limit number of tickers to process (useful for testing)",
    )

    parser.add_argument(
        "--no-headless",
        action="store_true",
        help="Show browser during scraping (for debugging)",
    )

    parser.add_argument(
        "--tickers",
        "-t",
        type=str,
        default=None,
        help='Comma-separated list of tickers (e.g., "NUE, RYAAY")',
    )

    parser.add_argument(
        "--tickers-file",
        type=str,
        default=None,
        help="Path to file containing tickers (comma-separated or one per line). "
        "e.g., tickers_from_spreadsheet.txt generated by update_extended_hours_prices.py",
    )

    parser.add_argument(
        "--concurrency",
        "-c",
        type=int,
        default=3,
        help="Number of concurrent scraping sessions (default: 3)",
    )

    parser.add_argument(
        "--quarter-mode",
        "-q",
        choices=["forecast", "reported"],
        default="forecast",
        help="Quarter anchor mode: 'forecast' uses next unreported quarter (default), 'reported' uses last reported quarter",
    )

    parser.add_argument(
        "--expand-to-near-by-days",
        "-r",
        type=int,
        default=0,
        help="Expand date coverage by this many days on both sides. "
        "e.g., --date 2026-01-15 --expand-to-near-by-days 3 covers 2026-01-12 to 2026-01-18 (default: 0, single day)",
    )

    # Google Sheets arguments
    parser.add_argument(
        "--spreadsheet-id",
        required=True,
        help="Google Sheets spreadsheet ID (from the URL)",
    )

    parser.add_argument(
        "--tab-name",
        default=None,
        help="Name of the tab to write to. Default: Earnings_YYYY-MM-DD",
    )

    parser.add_argument(
        "--no-clear",
        action="store_true",
        help="Do not clear existing data before writing (append mode)",
    )

    parser.add_argument(
        "--no-format",
        action="store_true",
        help="Do not format the header row",
    )

    parser.add_argument(
        "--keep-csv",
        action="store_true",
        help="Keep the local CSV file after uploading (default: delete)",
    )

    parser.add_argument(
        "--skip-upload",
        action="store_true",
        help="Skip Google Sheets upload (just generate CSV)",
    )

    parser.add_argument(
        "--skip-existing-tickers-col",
        type=str,
        default=None,
        help="Column letter containing existing tickers to skip (e.g., 'A'). "
        "Only processes tickers not already in this column.",
    )

    parser.add_argument(
        "--skip-existing-tickers-tab",
        type=str,
        default=None,
        help="Tab name to read existing tickers from. Defaults to --tab-name if not specified.",
    )

    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable verbose logging"
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Generate default filenames if not specified
    date_str = args.date.strftime("%Y-%m-%d")
    if args.output is None:
        args.output = f"earnings_analysis_{date_str}.csv"
    if args.tab_name is None:
        args.tab_name = f"Earnings_{date_str}"

    # Parse tickers filter
    tickers_filter = None
    if args.tickers:
        tickers_filter = [
            t.strip().upper() for t in args.tickers.split(",") if t.strip()
        ]
    elif args.tickers_file:
        tickers_file_path = Path(args.tickers_file)
        if not tickers_file_path.exists():
            logger.error(f"Tickers file not found: {args.tickers_file}")
            sys.exit(1)
        with open(tickers_file_path, "r") as f:
            content = f.read()
        # Support both comma-separated and one-per-line formats
        if "," in content:
            tickers_filter = [
                t.strip().upper() for t in content.split(",") if t.strip()
            ]
        else:
            tickers_filter = [
                t.strip().upper() for t in content.splitlines() if t.strip()
            ]
        logger.info(f"Loaded {len(tickers_filter)} tickers from {args.tickers_file}")

    # Filter out existing tickers if specified
    if args.skip_existing_tickers_col and tickers_filter:
        existing_tab = args.skip_existing_tickers_tab or args.tab_name
        logger.info(
            f"Checking for existing tickers in {existing_tab}!{args.skip_existing_tickers_col}..."
        )
        client = create_sheets_client()
        existing_tickers = get_existing_tickers_from_sheet(
            client=client,
            spreadsheet_id=args.spreadsheet_id,
            tab_name=existing_tab,
            ticker_col=args.skip_existing_tickers_col,
        )
        if existing_tickers:
            original_count = len(tickers_filter)
            tickers_filter = [t for t in tickers_filter if t not in existing_tickers]
            skipped_count = original_count - len(tickers_filter)
            if skipped_count > 0:
                logger.info(
                    f"Skipping {skipped_count} existing tickers, {len(tickers_filter)} new tickers to process"
                )
            if not tickers_filter:
                logger.info(
                    "All tickers already exist in the spreadsheet, nothing to process"
                )

    try:
        # Step 1: Generate earnings analysis
        logger.info("=" * 80)
        logger.info("Step 1: Generating earnings analysis...")
        logger.info("=" * 80)

        rows = generate_earnings_analysis(
            date=args.date,
            output_filename=args.output,
            limit=args.limit,
            headless=not args.no_headless,
            tickers_filter=tickers_filter,
            concurrency=args.concurrency,
            quarter_mode=args.quarter_mode,
            date_range_days=args.expand_to_near_by_days,
        )

        if not rows:
            logger.warning("No data generated, skipping upload")
            return

        # Step 2: Upload to Google Sheets
        if not args.skip_upload:
            logger.info("")
            logger.info("=" * 80)
            logger.info("Step 2: Uploading to Google Sheets...")
            logger.info("=" * 80)

            upload_csv_to_sheets(
                csv_file=args.output,
                spreadsheet_id=args.spreadsheet_id,
                tab_name=args.tab_name,
                clear_existing=not args.no_clear,
                format_header=not args.no_format,
            )

        # Step 3: Cleanup
        if not args.keep_csv and not args.skip_upload:
            csv_path = Path(args.output)
            if csv_path.exists():
                csv_path.unlink()
                logger.info(f"Cleaned up local CSV file: {args.output}")

        logger.info("")
        logger.info("=" * 80)
        logger.info("All done!")
        logger.info("=" * 80)

    except KeyboardInterrupt:
        logger.info("\n\nInterrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error: {e}")
        if args.verbose:
            import traceback

            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
