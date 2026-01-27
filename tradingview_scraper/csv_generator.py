#!/usr/bin/env python3
"""
Helper functions for generating CSV output with earnings analysis data.
"""

import csv
from typing import List, Dict
from metrics_calculator import (
    format_market_cap,
    format_revenue,
    format_number,
)


def get_csv_headers() -> List[str]:
    """
    Get the standard CSV headers for earnings analysis.

    Returns:
        List of column headers
    """
    return [
        "ticker",
        "hot?",
        "Note",
        "Company name",
        "Market segment",
        "Market Cap (B)",
        "Current Quarter",
        "EPS Q Est.",
        "EPS Q actual",
        "Rev Q est.",
        "Rev Q actual",
        "EPS same Q last Y",
        "Rev same Q last Y",
        "Rev last Q",
        "Rev last Q last Y",
        "Rev full Y Est.",
        "Rev full Y last Y",
        "Rev Y actual 2 Y ago",
    ]


def build_csv_row(api_data: Dict, yoy_data: Dict) -> Dict:
    """
    Build a single CSV row from API data and YoY data.

    Args:
        api_data: Data from earnings API
        yoy_data: Year-over-year comparison data from scraper

    Returns:
        Dictionary with all CSV columns
    """
    # EPS data from API (current quarter)
    eps_q_est = api_data.get("eps_q_estimate")
    eps_q_actual = api_data.get("eps_q_actual")

    # Revenue data from API (current quarter) - convert to millions
    rev_q_est_raw = api_data.get("revenue_q_estimate")
    rev_q_actual_raw = api_data.get("revenue_q_actual")
    rev_q_est = rev_q_est_raw / 1_000_000 if rev_q_est_raw else None
    rev_q_actual = rev_q_actual_raw / 1_000_000 if rev_q_actual_raw else None

    # Historical data from scraper (already in millions for revenue)
    eps_same_q_last_y = yoy_data.get("eps_same_q_last_y")
    rev_same_q_last_y = yoy_data.get("rev_same_q_last_y")
    rev_last_q = yoy_data.get("rev_last_q")
    rev_last_q_last_y = yoy_data.get("rev_last_q_last_y")

    # Annual data from scraper
    rev_full_y_est = yoy_data.get("rev_full_y_est")
    rev_full_y_last_y = yoy_data.get("rev_full_y_last_y")
    rev_y_2y_ago = yoy_data.get("rev_y_2y_ago")

    # Current quarter from scraper
    current_quarter = yoy_data.get("current_quarter", "")

    # Build row
    row = {
        "ticker": api_data.get("ticker", ""),
        "hot?": "",
        "Note": "",
        "Company name": api_data.get("company_name", ""),
        "Market segment": api_data.get("sector", ""),
        "Market Cap (B)": format_market_cap(api_data.get("market_cap")),
        "Current Quarter": current_quarter,
        "EPS Q Est.": format_number(eps_q_est),
        "EPS Q actual": format_number(eps_q_actual),
        "Rev Q est.": format_revenue(rev_q_est),
        "Rev Q actual": format_revenue(rev_q_actual),
        "EPS same Q last Y": format_number(eps_same_q_last_y),
        "Rev same Q last Y": format_revenue(rev_same_q_last_y),
        "Rev last Q": format_revenue(rev_last_q),
        "Rev last Q last Y": format_revenue(rev_last_q_last_y),
        "Rev full Y Est.": format_revenue(rev_full_y_est),
        "Rev full Y last Y": format_revenue(rev_full_y_last_y),
        "Rev Y actual 2 Y ago": format_revenue(rev_y_2y_ago),
    }

    return row


def save_to_csv(data: List[Dict], filename: str):
    """
    Save earnings analysis data to CSV file.

    Args:
        data: List of row dictionaries
        filename: Output CSV filename
    """
    if not data:
        print("No data to save")
        return

    headers = get_csv_headers()

    with open(filename, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=headers)
        writer.writeheader()
        writer.writerows(data)

    print(f"\n✓ Saved {len(data)} rows to {filename}")
