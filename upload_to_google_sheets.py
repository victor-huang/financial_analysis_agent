#!/usr/bin/env python3
"""
Example script demonstrating how to upload CSV data to Google Sheets.

This script can be used to upload earnings data or any other CSV file
to a Google Sheets document.
"""

import argparse
import json
import logging
import sys
from pathlib import Path

from financial_analysis_agent.config import get_config
from financial_analysis_agent.export import GoogleSheetsClient

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def create_sheets_client() -> GoogleSheetsClient:
    """
    Create and return a GoogleSheetsClient using credentials from config.

    Returns:
        GoogleSheetsClient instance

    Raises:
        ValueError: If credentials are not configured
        Exception: If client creation fails
    """
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


def upload_csv_to_sheets(
    csv_file: str,
    spreadsheet_id: str,
    tab_name: str,
    clear_existing: bool = True,
    format_header: bool = True,
) -> None:
    """
    Upload a CSV file to Google Sheets.

    Args:
        csv_file: Path to CSV file
        spreadsheet_id: Google Sheets spreadsheet ID
        tab_name: Name of the tab to write to
        clear_existing: Whether to clear existing data
        format_header: Whether to format the header row
    """
    try:
        # Create client
        logger.info("Initializing Google Sheets client...")
        client = create_sheets_client()

        # Upload CSV
        logger.info(f"Uploading {csv_file} to sheet tab '{tab_name}'...")
        result = client.write_csv_to_sheet(
            spreadsheet_id=spreadsheet_id,
            csv_file=csv_file,
            tab_name=tab_name,
            clear_existing=clear_existing,
        )

        # Format header row
        if format_header:
            logger.info("Formatting header row...")
            client.format_header_row(
                spreadsheet_id=spreadsheet_id,
                tab_name=tab_name,
                bold=True,
                background_color={"red": 0.9, "green": 0.9, "blue": 0.9},
            )

        logger.info(f"✓ Successfully uploaded data to Google Sheets!")
        logger.info(
            f"  Spreadsheet: https://docs.google.com/spreadsheets/d/{spreadsheet_id}"
        )
        logger.info(f"  Tab: {tab_name}")
        logger.info(f"  Rows updated: {result.get('updatedRows', 'N/A')}")

    except FileNotFoundError as e:
        logger.error(f"CSV file not found: {e}")
        sys.exit(1)
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Failed to upload to Google Sheets: {e}")
        sys.exit(1)


def main():
    """Main execution function."""
    parser = argparse.ArgumentParser(
        description="Upload CSV data to Google Sheets",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Upload tradingview earnings to a Google Sheet
  python upload_to_google_sheets.py \\
    --csv tradingview_earnings.csv \\
    --spreadsheet-id 1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms \\
    --tab-name "Earnings_2025-11-11"

  # Upload analysis data
  python upload_to_google_sheets.py \\
    --csv aapl_analysis.csv \\
    --spreadsheet-id 1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms \\
    --tab-name "AAPL_Analysis" \\
    --no-clear

Setup:
  1. Create a Google Cloud project and enable Google Sheets API
  2. Create a service account and download the JSON credentials
  3. Share your Google Sheet with the service account email
  4. Set GOOGLE_SHEETS_CREDENTIALS_PATH in your .env file
  5. Run this script with your spreadsheet ID and desired tab name

Getting the spreadsheet ID:
  From the URL: https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/edit
  Copy the value between '/d/' and '/edit'
        """,
    )

    parser.add_argument("--csv", required=True, help="Path to CSV file to upload")

    parser.add_argument(
        "--spreadsheet-id",
        required=True,
        help="Google Sheets spreadsheet ID (from the URL)",
    )

    parser.add_argument(
        "--tab-name",
        default="Sheet1",
        help="Name of the tab to write to (default: Sheet1)",
    )

    parser.add_argument(
        "--no-clear",
        action="store_true",
        help="Do not clear existing data before writing",
    )

    parser.add_argument(
        "--no-format", action="store_true", help="Do not format the header row"
    )

    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable verbose logging"
    )

    args = parser.parse_args()

    # Set logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Validate CSV file exists
    csv_path = Path(args.csv)
    if not csv_path.exists():
        logger.error(f"CSV file not found: {args.csv}")
        sys.exit(1)

    # Upload to Google Sheets
    upload_csv_to_sheets(
        csv_file=args.csv,
        spreadsheet_id=args.spreadsheet_id,
        tab_name=args.tab_name,
        clear_existing=not args.no_clear,
        format_header=not args.no_format,
    )


if __name__ == "__main__":
    main()
