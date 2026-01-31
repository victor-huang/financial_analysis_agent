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
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import List, Dict, Tuple

# Import our helper modules
from earnings_api_helper import get_earnings_for_date, get_earnings_for_date_range
from financial_data_helper import FinancialDataFetcher
from csv_generator import build_csv_row, save_to_csv


def process_single_ticker(
    idx: int,
    total: int,
    ticker_data: Dict,
    headless: bool,
    quarter_mode: str = "forecast",
) -> Tuple[int, Dict, str]:
    """
    Process a single ticker - used by concurrent executor.

    Args:
        idx: Index of this ticker (for ordering)
        total: Total number of tickers
        ticker_data: API data for this ticker
        headless: Run browser in headless mode
        quarter_mode: 'forecast' for next unreported quarter, 'reported' for last reported

    Returns:
        Tuple of (index, row_dict, warning_message or None)
    """
    ticker = ticker_data["ticker"]
    exchange = ticker_data["exchange"]

    print(f"\n[{idx}/{total}] Processing {ticker} ({exchange})...")

    fetcher = FinancialDataFetcher(headless=headless)
    warning = None

    try:
        yoy_data = fetcher.get_yoy_data(ticker, exchange, quarter_mode=quarter_mode)
        if not yoy_data:
            print(f"  [{ticker}] Warning: No historical data available")
            warning = f"{ticker} (no forecast data)"
    except Exception as e:
        print(f"  [{ticker}] Error fetching YoY data: {e}")
        yoy_data = {}
        warning = f"{ticker} (error: {str(e)[:50]})"
    finally:
        fetcher.close()

    row = build_csv_row(ticker_data, yoy_data)
    print(f"  [{ticker}] Row completed")

    return (idx, row, warning)


def generate_earnings_analysis(
    date: datetime,
    output_filename: str,
    limit: int = None,
    headless: bool = True,
    tickers_filter: List[str] = None,
    concurrency: int = 3,
    quarter_mode: str = "forecast",
    date_range_days: int = 0,
) -> List[Dict]:
    """
    Generate complete earnings analysis by combining API and scraper data.

    Args:
        date: Date to fetch earnings for
        output_filename: Output CSV filename
        limit: Maximum number of tickers to process (None = all)
        headless: Run browser in headless mode
        tickers_filter: List of specific tickers to process (None = all)
        concurrency: Number of concurrent scraping sessions (default: 3)
        quarter_mode: 'forecast' for next unreported quarter, 'reported' for last reported
        date_range_days: Number of days to expand date range on both sides (0 = single day)

    Returns:
        List of row dictionaries
    """
    print(f"\n{'='*80}")
    print(f"Generating Earnings Analysis CSV")
    if date_range_days > 0:
        start_date = date - timedelta(days=date_range_days)
        end_date = date + timedelta(days=date_range_days)
        print(
            f"Date Range: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')} (center: {date.strftime('%Y-%m-%d')}, +/- {date_range_days} days)"
        )
    else:
        print(f"Date: {date.strftime('%Y-%m-%d')}")
    print(f"Output: {output_filename}")
    if tickers_filter:
        print(f"Filter: {', '.join(tickers_filter)}")
    print("=" * 80)

    # Step 1: Fetch earnings from API
    print("\nStep 1: Fetching earnings calendar data...")
    if date_range_days > 0:
        start_date = date - timedelta(days=date_range_days)
        end_date = date + timedelta(days=date_range_days)
        api_data = get_earnings_for_date_range(start_date, end_date)
    else:
        api_data = get_earnings_for_date(date)

    if not api_data:
        print("No earnings found for this date")
        return []

    # Apply ticker filter if specified
    missing_tickers = []
    tickers_order = None  # Original order to maintain in output
    if tickers_filter:
        tickers_upper = [t.upper() for t in tickers_filter]
        tickers_order = tickers_upper  # Save for later ordering
        # Create a dict for quick lookup
        api_data_by_ticker = {d["ticker"].upper(): d for d in api_data}
        # Preserve the order from tickers_filter, track missing ones
        api_data = []
        for t in tickers_upper:
            if t in api_data_by_ticker:
                api_data.append(api_data_by_ticker[t])
            else:
                missing_tickers.append(t)
        if api_data:
            print(
                f"  Found {len(api_data)} ticker(s) in earnings calendar: {', '.join(d['ticker'] for d in api_data)}"
            )
        if missing_tickers:
            print(
                f"  {len(missing_tickers)} ticker(s) not found in earnings calendar: {', '.join(missing_tickers)}"
            )

    # Apply limit if specified
    if limit:
        api_data = api_data[:limit]
        print(f"  Limited to first {limit} tickers")

    # Step 2: Fetch detailed financial data for each ticker
    if api_data:
        print(
            f"\nStep 2: Fetching detailed financial data for {len(api_data)} tickers..."
        )
        print(f"  Using {concurrency} concurrent session(s)")

    total = len(api_data)
    results = []
    skipped_tickers = []

    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = {
            executor.submit(
                process_single_ticker, idx, total, ticker_data, headless, quarter_mode
            ): idx
            for idx, ticker_data in enumerate(api_data, 1)
        }

        for future in as_completed(futures):
            try:
                idx, row, warning = future.result()
                results.append((idx, row))
                if warning:
                    skipped_tickers.append(warning)
            except Exception as e:
                idx = futures[future]
                print(f"  Error processing ticker at index {idx}: {e}")

    # Build final rows maintaining original ticker order
    if tickers_order:
        # Create a dict of ticker -> row from processed results
        rows_by_ticker = {row["ticker"].upper(): row for _, row in results}
        rows = []
        for ticker in tickers_order:
            if ticker in rows_by_ticker:
                rows.append(rows_by_ticker[ticker])
            else:
                # Create placeholder row for missing ticker
                placeholder_row = build_csv_row({"ticker": ticker}, {})
                rows.append(placeholder_row)
    else:
        # No filter specified, use original processing order
        results.sort(key=lambda x: x[0])
        rows = [row for _, row in results]

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

    if missing_tickers:
        print(
            f"\n⚠  Note: {len(missing_tickers)} ticker(s) not found in earnings calendar (added as placeholder rows):"
        )
        for ticker in missing_tickers:
            print(f"   - {ticker}")

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
  # Generate analysis for today's earnings (default settings)
  python generate_earnings_analysis.py

  # Generate for a specific date
  python generate_earnings_analysis.py --date 2025-01-15

  # Limit to first 5 tickers (useful for testing)
  python generate_earnings_analysis.py --limit 5

  # Filter to specific tickers only
  python generate_earnings_analysis.py --tickers "NUE, RYAAY"

  # Custom output filename
  python generate_earnings_analysis.py --output my_earnings.csv

  # Use 5 concurrent scraping sessions (default: 3)
  python generate_earnings_analysis.py --concurrency 5

  # Use reported quarter mode (last reported quarter as anchor)
  # Default is 'forecast' which uses next unreported quarter
  python generate_earnings_analysis.py --quarter-mode reported

  # Show browser during scraping (for debugging)
  python generate_earnings_analysis.py --no-headless

  # Combined example: specific tickers with 5 concurrent sessions
  python generate_earnings_analysis.py -t "AAPL, MSFT, GOOGL" -c 5 -o tech_earnings.csv

  # Expand date range by 3 days on each side (covers 7 days total)
  # e.g., --date 2026-01-15 --expand-to-near-by-days 3 covers 2026-01-12 to 2026-01-18
  python generate_earnings_analysis.py --date 2026-01-15 --expand-to-near-by-days 3

Quarter Modes:
  forecast (default): Uses next unreported quarter as "Current Quarter"
                      Best for companies about to report earnings
  reported:           Uses last reported quarter as "Current Quarter"
                      Best for companies that have already reported
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
            concurrency=args.concurrency,
            quarter_mode=args.quarter_mode,
            date_range_days=args.expand_to_near_by_days,
        )
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
