#!/usr/bin/env python3
"""
Fetch current day's earnings data from TradingView and export to CSV.
"""

import requests
import csv
import json
import argparse
from datetime import datetime, time, timedelta


def fetch_tradingview_earnings(start_timestamp, end_timestamp):
    """
    Fetch earnings data from TradingView scanner API.

    Args:
        start_timestamp: Unix timestamp for start of date range
        end_timestamp: Unix timestamp for end of date range

    Returns:
        dict: JSON response from TradingView API
    """
    url = "https://scanner.tradingview.com/america/scan"

    params = {
        "label-product": "screener-stock-old"
    }

    headers = {
        "accept": "text/plain, */*; q=0.01",
        "accept-language": "en-US,en;q=0.9",
        "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
        "origin": "https://www.tradingview.com",
        "referer": "https://www.tradingview.com/",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-site",
        "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
    }

    payload = {
        "filter": [
            {
                "left": "is_primary",
                "operation": "equal",
                "right": True
            },
            {
                "left": "earnings_release_date,earnings_release_next_date",
                "operation": "in_range",
                "right": [start_timestamp, end_timestamp]
            },
            {
                "left": "earnings_release_date,earnings_release_next_date",
                "operation": "nequal",
                "right": end_timestamp
            }
        ],
        "options": {
            "lang": "en"
        },
        "markets": ["america"],
        "symbols": {
            "query": {
                "types": []
            },
            "tickers": []
        },
        "columns": [
            "logoid",
            "name",
            "market_cap_basic",
            "earnings_per_share_forecast_next_fq",
            "earnings_per_share_fq",
            "eps_surprise_fq",
            "eps_surprise_percent_fq",
            "revenue_forecast_next_fq",
            "revenue_fq",
            "earnings_release_next_date",
            "earnings_release_next_calendar_date",
            "earnings_release_next_time",
            "description",
            "type",
            "subtype",
            "update_mode",
            "earnings_per_share_forecast_fq",
            "revenue_forecast_fq",
            "earnings_release_date",
            "earnings_release_calendar_date",
            "earnings_release_time",
            "currency",
            "fundamental_currency_code"
        ],
        "sort": {
            "sortBy": "market_cap_basic",
            "sortOrder": "desc"
        },
        "preset": None,
        "range": [0, 450]
    }

    response = requests.post(url, params=params, headers=headers, json=payload)
    response.raise_for_status()

    return response.json()


def extract_earnings_data(response_data):
    """
    Extract ticker, EPS, revenue, and estimates from TradingView response.

    Args:
        response_data: JSON response from TradingView API

    Returns:
        list: List of dictionaries with ticker, eps, revenue, and estimates data
    """
    results = []

    if "data" not in response_data:
        print("Warning: No 'data' field in response")
        return results

    for item in response_data["data"]:
        # item structure: {"s": "TICKER", "d": [values...]}
        ticker_full = item.get("s", "")
        data_values = item.get("d", [])

        # Remove exchange prefix (e.g., "NYSE:AAPL" -> "AAPL")
        ticker = ticker_full.split(":")[-1] if ":" in ticker_full else ticker_full

        # Find the indices for the columns we need
        # Based on the columns list in the request:
        # Index 4: earnings_per_share_fq (current quarter actual EPS)
        # Index 8: revenue_fq (current quarter actual revenue)
        # Index 16: earnings_per_share_forecast_fq (estimated EPS for current quarter)
        # Index 17: revenue_forecast_fq (estimated revenue for current quarter)

        eps_fq = data_values[4] if len(data_values) > 4 else None
        revenue_fq = data_values[8] if len(data_values) > 8 else None
        estimated_eps = data_values[16] if len(data_values) > 16 else None
        estimated_revenue = data_values[17] if len(data_values) > 17 else None

        results.append({
            "Ticker": ticker,
            "Current Quarter EPS": eps_fq,
            "Current Quarter Revenue": revenue_fq,
            "Estimated EPS": estimated_eps,
            "Estimated Revenue": estimated_revenue
        })

    return results


def save_to_csv(data, filename="tradingview_earnings.csv"):
    """
    Save earnings data to CSV file.

    Args:
        data: List of dictionaries with earnings data
        filename: Output CSV filename
    """
    if not data:
        print("No data to save")
        return

    with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
        fieldnames = ["Ticker", "Current Quarter EPS", "Current Quarter Revenue", "Estimated EPS", "Estimated Revenue"]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

        writer.writeheader()
        writer.writerows(data)

    print(f"Saved {len(data)} earnings records to {filename}")


def parse_date(date_string):
    """
    Parse date string in YYYY-MM-DD format.

    Args:
        date_string: Date string to parse

    Returns:
        datetime: Parsed datetime object
    """
    try:
        return datetime.strptime(date_string, '%Y-%m-%d')
    except ValueError:
        raise argparse.ArgumentTypeError(f"Invalid date format: {date_string}. Use YYYY-MM-DD")


def main():
    """Main execution function."""
    parser = argparse.ArgumentParser(
        description="Fetch earnings data from TradingView and export to CSV",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Fetch today's earnings (default)
  python fetch_tradingview_earnings.py

  # Fetch earnings for a specific date
  python fetch_tradingview_earnings.py --date 2025-11-05

  # Fetch earnings for a date range
  python fetch_tradingview_earnings.py --start-date 2025-11-01 --end-date 2025-11-05

  # Specify custom output file
  python fetch_tradingview_earnings.py --output earnings_data.csv
        """
    )

    parser.add_argument(
        '--date',
        type=parse_date,
        help='Specific date to fetch earnings for (YYYY-MM-DD). Defaults to today.'
    )

    parser.add_argument(
        '--start-date',
        type=parse_date,
        help='Start date for date range (YYYY-MM-DD). Overrides --date.'
    )

    parser.add_argument(
        '--end-date',
        type=parse_date,
        help='End date for date range (YYYY-MM-DD). Overrides --date.'
    )

    parser.add_argument(
        '--output',
        '-o',
        default='tradingview_earnings.csv',
        help='Output CSV filename (default: tradingview_earnings.csv)'
    )

    args = parser.parse_args()

    # Determine date range
    if args.start_date and args.end_date:
        # Use explicit date range
        start_dt = datetime.combine(args.start_date, time.min)
        end_dt = datetime.combine(args.end_date, time.max)
    elif args.date:
        # Use specific date (full day)
        start_dt = datetime.combine(args.date, time.min)
        end_dt = datetime.combine(args.date, time.max)
    else:
        # Default to today
        today = datetime.now().date()
        start_dt = datetime.combine(today, time.min)
        end_dt = datetime.combine(today, time.max)

    # Convert to Unix timestamps
    start_timestamp = int(start_dt.timestamp())
    end_timestamp = int(end_dt.timestamp())

    print(f"Fetching earnings data from TradingView...")
    print(f"Date range: {start_dt.strftime('%Y-%m-%d %H:%M:%S')} to {end_dt.strftime('%Y-%m-%d %H:%M:%S')}")

    try:
        # Fetch data from TradingView
        response_data = fetch_tradingview_earnings(start_timestamp, end_timestamp)

        # Extract relevant fields
        earnings_data = extract_earnings_data(response_data)

        # Save to CSV
        save_to_csv(earnings_data, args.output)

        print(f"\nSummary:")
        print(f"Total companies found: {len(earnings_data)}")

    except requests.exceptions.RequestException as e:
        print(f"Error fetching data: {e}")
    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    main()
