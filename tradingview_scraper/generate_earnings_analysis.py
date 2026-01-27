#!/usr/bin/env python3
"""
Generate comprehensive earnings analysis CSV by combining:
1. TradingView earnings API data (current quarter estimates/actuals)
2. TradingView scraper data (historical YoY comparisons)

Usage:
    python generate_earnings_analysis.py                    # Today's earnings
    python generate_earnings_analysis.py --date 2025-01-15  # Specific date
    python generate_earnings_analysis.py --limit 10         # Limit to first 10 tickers
"""

import argparse
from datetime import datetime
from typing import List, Dict

# Import our helper modules
from earnings_api_helper import get_earnings_for_date
from financial_data_helper import FinancialDataFetcher
from csv_generator import build_csv_row, save_to_csv


def generate_earnings_analysis(
    date: datetime,
    output_filename: str,
    limit: int = None,
    headless: bool = True,
    tickers_filter: List[str] = None,
) -> List[Dict]:
    """
    Generate complete earnings analysis by combining API and scraper data.

    Args:
        date: Date to fetch earnings for
        output_filename: Output CSV filename
        limit: Maximum number of tickers to process (None = all)
        headless: Run browser in headless mode
        tickers_filter: List of specific tickers to process (None = all)

    Returns:
        List of row dictionaries
    """
    print(f"\n{'='*80}")
    print(f"Generating Earnings Analysis CSV")
    print(f"Date: {date.strftime('%Y-%m-%d')}")
    print(f"Output: {output_filename}")
    if tickers_filter:
        print(f"Filter: {', '.join(tickers_filter)}")
    print("=" * 80)

    # Step 1: Fetch earnings from API
    print("\nStep 1: Fetching earnings calendar data...")
    api_data = get_earnings_for_date(date)

    if not api_data:
        print("No earnings found for this date")
        return []

    # Apply ticker filter if specified
    if tickers_filter:
        tickers_upper = [t.upper() for t in tickers_filter]
        # Create a dict for quick lookup
        api_data_by_ticker = {d["ticker"].upper(): d for d in api_data}
        # Preserve the order from tickers_filter
        api_data = [
            api_data_by_ticker[t] for t in tickers_upper if t in api_data_by_ticker
        ]
        print(
            f"  Filtered to {len(api_data)} ticker(s): {', '.join(d['ticker'] for d in api_data)}"
        )
        if not api_data:
            print("  No matching tickers found in earnings calendar")
            return []

    # Apply limit if specified
    if limit:
        api_data = api_data[:limit]
        print(f"  Limited to first {limit} tickers")

    # Step 2: Fetch detailed financial data for each ticker
    print(f"\nStep 2: Fetching detailed financial data for {len(api_data)} tickers...")
    print("  (This may take several minutes as we scrape each ticker)")

    fetcher = FinancialDataFetcher(headless=headless)
    rows = []
    skipped_tickers = []

    for idx, ticker_data in enumerate(api_data, 1):
        ticker = ticker_data["ticker"]
        exchange = ticker_data["exchange"]

        print(f"\n[{idx}/{len(api_data)}] Processing {ticker} ({exchange})...")

        # Get YoY comparison data from scraper
        try:
            yoy_data = fetcher.get_yoy_data(ticker, exchange)
            if not yoy_data:
                print(
                    f"  ⚠ Warning: No historical data available (likely no forecast page)"
                )
                skipped_tickers.append(f"{ticker} (no forecast data)")
        except Exception as e:
            print(f"  ✗ Error fetching YoY data: {e}")
            yoy_data = {}
            skipped_tickers.append(f"{ticker} (error: {str(e)[:50]})")

        # Build CSV row
        row = build_csv_row(ticker_data, yoy_data)
        rows.append(row)

        print(f"  ✓ Row completed")

    # Close the scraper
    fetcher.close()

    # Step 3: Save to CSV
    print(f"\nStep 3: Saving results...")
    save_to_csv(rows, output_filename)

    print(f"\n{'='*80}")
    print(f"Analysis Complete!")
    print(f"Processed {len(rows)} tickers")
    print(f"Output saved to: {output_filename}")

    if skipped_tickers:
        print(
            f"\n⚠  Warning: {len(skipped_tickers)} ticker(s) missing historical data:"
        )
        for ticker_info in skipped_tickers:
            print(f"   - {ticker_info}")
        print("\nNote: Small-cap stocks often lack TradingView forecast pages.")
        print("      Only API data (current estimates/actuals) is available for these.")

    print("=" * 80)

    return rows


def parse_date(date_string: str) -> datetime:
    """Parse date string in YYYY-MM-DD format."""
    try:
        return datetime.strptime(date_string, "%Y-%m-%d")
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"Invalid date format: {date_string}. Use YYYY-MM-DD"
        )


def main():
    """Main execution function."""
    parser = argparse.ArgumentParser(
        description="Generate earnings analysis CSV combining API and scraper data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate analysis for today's earnings
  python generate_earnings_analysis.py

  # Generate for a specific date
  python generate_earnings_analysis.py --date 2025-01-15

  # Limit to first 5 tickers (useful for testing)
  python generate_earnings_analysis.py --limit 5

  # Filter to specific tickers only
  python generate_earnings_analysis.py --tickers "NUE, RYAAY"

  # Show browser during scraping (for debugging)
  python generate_earnings_analysis.py --no-headless

  # Custom output filename
  python generate_earnings_analysis.py --output my_earnings.csv
        """,
    )

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
        help='Comma-separated list of tickers to filter (e.g., "NUE, RYAAY")',
    )

    args = parser.parse_args()

    # Generate default filename if not specified
    if args.output is None:
        date_str = args.date.strftime("%Y-%m-%d")
        args.output = f"earnings_analysis_{date_str}.csv"

    # Parse tickers filter
    tickers_filter = None
    if args.tickers:
        tickers_filter = [t.strip() for t in args.tickers.split(",")]

    try:
        generate_earnings_analysis(
            date=args.date,
            output_filename=args.output,
            limit=args.limit,
            headless=not args.no_headless,
            tickers_filter=tickers_filter,
        )
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
