#!/usr/bin/env python3
"""
Helper functions for fetching earnings data from TradingView API.
"""

import requests
from datetime import date, datetime, time, timezone
from typing import Dict, List, Optional, Tuple

SCANNER_URL = "https://scanner.tradingview.com/america/scan"
SCANNER_HEADERS = {
    "origin": "https://www.tradingview.com",
    "referer": "https://www.tradingview.com/",
    "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
}
RELEASE_SCHEDULE_COLUMNS = [
    "fiscal_period_current",
    "fiscal_period_end_fq",
    "earnings_release_date",
    "earnings_release_next_date",
]


def _timestamp_to_date(timestamp: Optional[float]) -> Optional[date]:
    if timestamp is None:
        return None
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).date()


def fetch_release_schedules(keys: List[Tuple[str, str]]) -> Dict[Tuple[str, str], Dict]:
    """
    Fetch each ticker's latest reported fiscal quarter and its last/next
    earnings release dates from TradingView's scanner API, in one request.

    Args:
        keys: (exchange, ticker) tuples, using TradingView's exchange prefixes

    Returns:
        {(exchange, ticker): {"fiscal_period_current": "2026-Q2" or None,
                              "fiscal_period_end_date": date or None,
                              "last_release_date": date or None,
                              "next_release_date": date or None}}
        Tickers the scanner doesn't return are omitted.
    """
    payload = {
        "symbols": {"tickers": [f"{exchange}:{ticker}" for exchange, ticker in keys]},
        "columns": RELEASE_SCHEDULE_COLUMNS,
    }
    response = requests.post(SCANNER_URL, headers=SCANNER_HEADERS, json=payload, timeout=15)
    response.raise_for_status()

    schedules = {}
    for item in response.json().get("data", []):
        exchange, ticker = item["s"].split(":", 1)
        fiscal_period_current, fiscal_period_end, last_release, next_release = item["d"]
        schedules[(exchange, ticker)] = {
            "fiscal_period_current": fiscal_period_current,
            "fiscal_period_end_date": _timestamp_to_date(fiscal_period_end),
            "last_release_date": _timestamp_to_date(last_release),
            "next_release_date": _timestamp_to_date(next_release),
        }
    return schedules


def fetch_earnings_from_api(start_timestamp: int, end_timestamp: int) -> Dict:
    """
    Fetch earnings data from TradingView scanner API.

    Args:
        start_timestamp: Unix timestamp for start of date range
        end_timestamp: Unix timestamp for end of date range

    Returns:
        dict: JSON response from TradingView API
    """
    url = "https://scanner.tradingview.com/america/scan"

    params = {"label-product": "screener-stock-old"}

    headers = {
        "accept": "text/plain, */*; q=0.01",
        "accept-language": "en-US,en;q=0.9",
        "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
        "origin": "https://www.tradingview.com",
        "referer": "https://www.tradingview.com/",
        "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    }

    payload = {
        "filter": [
            {"left": "is_primary", "operation": "equal", "right": True},
            {
                "left": "earnings_release_date,earnings_release_next_date",
                "operation": "in_range",
                "right": [start_timestamp, end_timestamp],
            },
        ],
        "options": {"lang": "en"},
        "markets": ["america"],
        "symbols": {"query": {"types": []}, "tickers": []},
        "columns": [
            "logoid",
            "name",
            "description",
            "type",
            "subtype",
            "market_cap_basic",
            "earnings_per_share_forecast_fq",
            "earnings_per_share_fq",
            "eps_surprise_fq",
            "eps_surprise_percent_fq",
            "revenue_forecast_fq",
            "revenue_fq",
            "earnings_release_date",
            "earnings_release_next_date",
            "sector",
            "industry",
            "currency",
        ],
        "sort": {"sortBy": "market_cap_basic", "sortOrder": "desc"},
        "range": [0, 450],
    }

    response = requests.post(url, params=params, headers=headers, json=payload)
    response.raise_for_status()
    return response.json()


def parse_api_response(response_data: Dict) -> List[Dict]:
    """
    Parse TradingView API response into list of ticker data.

    Args:
        response_data: JSON response from TradingView API

    Returns:
        List of dictionaries with basic earnings data
    """
    results = []

    if "data" not in response_data:
        return results

    for item in response_data["data"]:
        ticker_full = item.get("s", "")
        data_values = item.get("d", [])

        # Extract ticker and exchange
        if ":" in ticker_full:
            exchange, ticker = ticker_full.split(":", 1)
        else:
            exchange = "UNKNOWN"
            ticker = ticker_full

        # Parse data based on column indices
        # data_values[1] is "name" (ticker symbol), data_values[2] is "description" (company name)
        company_name = data_values[2] if len(data_values) > 2 else ""
        market_cap = data_values[5] if len(data_values) > 5 else None
        eps_estimate = data_values[6] if len(data_values) > 6 else None
        eps_actual = data_values[7] if len(data_values) > 7 else None
        revenue_estimate = data_values[10] if len(data_values) > 10 else None
        revenue_actual = data_values[11] if len(data_values) > 11 else None
        sector = data_values[14] if len(data_values) > 14 else ""
        industry = data_values[15] if len(data_values) > 15 else ""

        results.append(
            {
                "ticker": ticker,
                "exchange": exchange,
                "company_name": company_name,
                "market_cap": market_cap,
                "sector": sector,
                "industry": industry,
                "eps_q_estimate": eps_estimate,
                "eps_q_actual": eps_actual,
                "revenue_q_estimate": revenue_estimate,
                "revenue_q_actual": revenue_actual,
            }
        )

    return results


def get_earnings_for_date(date: datetime) -> List[Dict]:
    """
    Get earnings data for a specific date.

    Args:
        date: Date to fetch earnings for

    Returns:
        List of earnings data dictionaries
    """
    start_dt = datetime.combine(date.date(), time.min)
    end_dt = datetime.combine(date.date(), time.max)

    start_timestamp = int(start_dt.timestamp())
    end_timestamp = int(end_dt.timestamp())

    print(f"Fetching earnings from API for {date.strftime('%Y-%m-%d')}...")

    response = fetch_earnings_from_api(start_timestamp, end_timestamp)
    earnings_data = parse_api_response(response)

    print(f"  Found {len(earnings_data)} companies with earnings")

    return earnings_data


def get_earnings_for_date_range(start_date: datetime, end_date: datetime) -> List[Dict]:
    """
    Get earnings data for a date range.

    Args:
        start_date: Start date of the range (inclusive)
        end_date: End date of the range (inclusive)

    Returns:
        List of earnings data dictionaries
    """
    start_dt = datetime.combine(start_date.date(), time.min)
    end_dt = datetime.combine(end_date.date(), time.max)

    start_timestamp = int(start_dt.timestamp())
    end_timestamp = int(end_dt.timestamp())

    print(
        f"Fetching earnings from API for {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}..."
    )

    response = fetch_earnings_from_api(start_timestamp, end_timestamp)
    earnings_data = parse_api_response(response)

    print(f"  Found {len(earnings_data)} companies with earnings")

    return earnings_data
