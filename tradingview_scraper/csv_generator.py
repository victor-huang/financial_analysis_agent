#!/usr/bin/env python3
"""
Helper functions for generating CSV output with earnings analysis data.
"""

import csv
from typing import List, Dict
from metrics_calculator import (
    calculate_beat_percentage,
    calculate_yoy_percentage,
    format_market_cap,
    format_revenue,
    format_percentage,
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
        "Fast grow?",
        "HC change (%)",
        "tech/analyst",
        "post gain $",
        "2nd day gain %",
        "EPS Q estimate",
        "EPS Q actual",
        "EPS beat %",
        "Revenue Q estimate",
        "revenue Q actual",
        "Revenue Q Beat %",
        "EPS Q last year",
        "EPS YoY %",
        "Revenue Q last year",
        "Revenue YoY %",
        "Revenue last Q YoY %",
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
    # Extract values
    eps_estimate = api_data.get("eps_q_estimate")
    eps_actual = api_data.get("eps_q_actual")
    revenue_estimate = api_data.get("revenue_q_estimate")
    revenue_actual = api_data.get("revenue_q_actual")

    # Convert API revenue from base units (dollars) to millions for consistency
    # API returns revenue in dollars, scraper returns in millions
    revenue_estimate_millions = (
        revenue_estimate / 1_000_000 if revenue_estimate else None
    )
    revenue_actual_millions = revenue_actual / 1_000_000 if revenue_actual else None

    eps_last_year = yoy_data.get("eps_last_year_q")
    revenue_last_year = yoy_data.get(
        "revenue_last_year_q"
    )  # Already in millions from scraper
    revenue_last_q = yoy_data.get("revenue_last_q")  # Already in millions from scraper

    # Calculate metrics (revenue values now all in millions)
    eps_beat_pct = calculate_beat_percentage(eps_actual, eps_estimate)
    revenue_beat_pct = calculate_beat_percentage(
        revenue_actual_millions, revenue_estimate_millions
    )
    eps_yoy_pct = calculate_yoy_percentage(eps_actual, eps_last_year)
    revenue_yoy_pct = calculate_yoy_percentage(
        revenue_actual_millions, revenue_last_year
    )
    revenue_last_q_yoy_pct = calculate_yoy_percentage(revenue_last_q, revenue_last_year)

    # Get employee headcount change
    employee_change_pct = yoy_data.get("employee_change_1y_percent")

    # Build row
    row = {
        "ticker": api_data.get("ticker", ""),
        "hot?": "",  # User input field
        "Note": "",  # User input field
        "Company name": api_data.get("company_name", ""),
        "Market segment": api_data.get("sector", ""),
        "Market Cap (B)": format_market_cap(api_data.get("market_cap")),
        "Fast grow?": "",  # User input field
        "HC change (%)": format_percentage(employee_change_pct),
        "tech/analyst": "",  # User input field
        "post gain $": "",  # Not available (post-earnings price movement)
        "2nd day gain %": "",  # Not available (post-earnings price movement)
        "EPS Q estimate": format_number(eps_estimate),
        "EPS Q actual": format_number(eps_actual),
        "EPS beat %": format_percentage(eps_beat_pct),
        "Revenue Q estimate": format_revenue(revenue_estimate_millions),
        "revenue Q actual": format_revenue(revenue_actual_millions),
        "Revenue Q Beat %": format_percentage(revenue_beat_pct),
        "EPS Q last year": format_number(eps_last_year),
        "EPS YoY %": format_percentage(eps_yoy_pct),
        "Revenue Q last year": format_revenue(revenue_last_year),
        "Revenue YoY %": format_percentage(revenue_yoy_pct),
        "Revenue last Q YoY %": format_percentage(revenue_last_q_yoy_pct),
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
