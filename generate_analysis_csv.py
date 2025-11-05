#!/usr/bin/env python3
"""
Generate a CSV file for earnings analysis from financial data JSON files.

Usage:
    python generate_analysis_csv.py <input_json> [output_csv] [--quarter YYYYQX]

By default, analyzes the current quarter (latest not-yet-reported quarter).
Use --quarter to specify a specific quarter for historical validation.

Examples:
    python generate_analysis_csv.py aapl.json                    # Analyze current quarter
    python generate_analysis_csv.py aapl.json --quarter 2025Q2   # Analyze specific quarter
"""

import json
import csv
import sys
import argparse
from pathlib import Path
from datetime import datetime


def parse_quarter_label(label):
    """Extract year and quarter from label like '2024Q3'"""
    if not label or "Q" not in label:
        return None, None
    parts = label.split("Q")
    if len(parts) == 2:
        try:
            year = int(parts[0])
            quarter = int(parts[1])
            return year, quarter
        except ValueError:
            return None, None
    return None, None


def find_latest_reported_quarter(eps_data):
    """Find the most recent earnings report with actual data (latest reported quarter)"""
    latest = None
    latest_date = None

    for eps in eps_data:
        eps_actual = eps.get("eps_actual")
        # Skip if no actual data or if it's NaN
        if eps_actual is None or (
            isinstance(eps_actual, float) and str(eps_actual) == "nan"
        ):
            continue

        announce_date = eps.get("announce_date")
        if announce_date:
            try:
                date_obj = datetime.fromisoformat(announce_date.replace("Z", "+00:00"))
                if latest_date is None or date_obj > latest_date:
                    latest_date = date_obj
                    latest = eps
            except:
                pass

    return latest


def get_next_quarter_label(quarter_label):
    """Get the next quarter label after the given quarter"""
    year, quarter = parse_quarter_label(quarter_label)
    if year is None or quarter is None:
        return None

    if quarter == 4:
        return f"{year + 1}Q1"
    else:
        return f"{year}Q{quarter + 1}"


def find_current_quarter(eps_data):
    """Find the current quarter (next unreported quarter after latest reported)"""
    latest_reported = find_latest_reported_quarter(eps_data)
    if not latest_reported:
        # If no reported quarters found, find the earliest quarter with estimates
        for eps in eps_data:
            if eps.get("eps_estimate") is not None:
                return eps.get("label")
        return None

    # Get the next quarter after latest reported
    latest_label = latest_reported.get("label")
    if not latest_label:
        return None

    next_label = get_next_quarter_label(latest_label)

    # Verify this quarter exists in the data
    for eps in eps_data:
        if eps.get("label") == next_label:
            return next_label

    return None


def find_quarter_data(data_list, quarter_label, data_type="eps"):
    """Find data for a specific quarter label

    Args:
        data_list: List of EPS or revenue data
        quarter_label: Quarter label like '2025Q2'
        data_type: 'eps' or 'revenue'

    Returns:
        Dictionary with the quarter's data, or None if not found
    """
    for item in data_list:
        if item.get("label") == quarter_label:
            return item
    return None


def find_prior_year_eps(eps_data, current_label):
    """Find EPS from the same quarter last year"""
    current_year, current_quarter = parse_quarter_label(current_label)
    if current_year is None or current_quarter is None:
        return None

    target_label = f"{current_year - 1}Q{current_quarter}"

    for eps in eps_data:
        if eps.get("label") == target_label and eps.get("eps_actual") is not None:
            return eps
    return None


def find_latest_reported_revenue(revenue_data):
    """Find the most recent revenue report with actual data (latest reported quarter)"""
    latest = None
    latest_date = None

    for rev in revenue_data:
        revenue_actual = rev.get("revenue_actual")
        # Skip if no actual data or if it's NaN
        if revenue_actual is None or (
            isinstance(revenue_actual, float) and str(revenue_actual) == "nan"
        ):
            continue

        period_end = rev.get("period_end")
        if period_end:
            try:
                date_obj = datetime.fromisoformat(period_end.replace("Z", "+00:00"))
                if latest_date is None or date_obj > latest_date:
                    latest_date = date_obj
                    latest = rev
            except:
                pass

    return latest


def find_prior_year_revenue(revenue_data, current_label):
    """Find revenue from the same quarter last year"""
    current_year, current_quarter = parse_quarter_label(current_label)
    if current_year is None or current_quarter is None:
        return None

    target_label = f"{current_year - 1}Q{current_quarter}"

    for rev in revenue_data:
        if rev.get("label") == target_label and rev.get("revenue_actual") is not None:
            return rev
    return None


def find_prior_quarter_revenue(revenue_data, current_label):
    """Find revenue from the previous quarter"""
    current_year, current_quarter = parse_quarter_label(current_label)
    if current_year is None or current_quarter is None:
        return None

    # Calculate previous quarter
    if current_quarter == 1:
        prev_year = current_year - 1
        prev_quarter = 4
    else:
        prev_year = current_year
        prev_quarter = current_quarter - 1

    target_label = f"{prev_year}Q{prev_quarter}"

    for rev in revenue_data:
        if rev.get("label") == target_label and rev.get("revenue_actual") is not None:
            return rev
    return None


def calculate_yoy_percentage(current, prior):
    """Calculate year-over-year percentage change"""
    if prior is None or prior == 0:
        return None
    return ((current - prior) / prior) * 100


def get_full_year_revenue_estimate(revenue_data, year):
    """Calculate full year revenue estimate by summing quarterly estimates

    Args:
        revenue_data: List of revenue data
        year: Year to calculate (e.g., 2025)

    Returns:
        Sum of quarterly estimates for the year, or None if insufficient data
    """
    quarters = {}

    # Collect unique quarters for the year
    for rev in revenue_data:
        label = rev.get('label', '')
        if label.startswith(str(year)) and 'Q' in label:
            est = rev.get('revenue_estimate')

            # Only use if we don't have this quarter yet or if this has better data
            if label not in quarters:
                quarters[label] = est
            elif est and str(est) != 'nan':
                quarters[label] = est

    # Sum up quarters Q1-Q4
    total = 0
    quarters_found = 0
    for q in [f"{year}Q1", f"{year}Q2", f"{year}Q3", f"{year}Q4"]:
        if q in quarters:
            est = quarters[q]
            if est and str(est) != 'nan':
                total += est
                quarters_found += 1

    # Only return if we have at least 3 quarters (reasonable estimate)
    if quarters_found >= 3:
        return total
    return None


def get_annual_revenue_actual(json_data, year):
    """Get full year actual revenue from historical data

    Args:
        json_data: The financial analysis JSON data
        year: Year to get (e.g., 2024)

    Returns:
        Annual revenue actual for the year, or None if not found
    """
    financial = json_data.get('financial', {})
    historical = financial.get('historical_ratios', {})
    annual = historical.get('annual', {})

    labels = annual.get('label', [])
    revenues = annual.get('revenue', [])

    year_str = str(year)
    if year_str in labels:
        idx = labels.index(year_str)
        return revenues[idx] * 1_000_000_000  # Convert to dollars (data is in billions)

    return None


def generate_csv_row(json_data, target_quarter=None):
    """Generate a CSV row from JSON data

    Args:
        json_data: The financial analysis JSON data
        target_quarter: Quarter label to analyze (e.g., '2025Q3').
                       If None, uses current quarter (latest unreported).

    Returns:
        Dictionary with CSV row data
    """
    ticker = json_data.get("ticker", "")
    financial = json_data.get("financial", {})
    company_info = financial.get("company_info", {})
    analyst_estimates = financial.get("analyst_estimates", {})

    # Basic company info
    company_name = company_info.get("name", "")
    sector = company_info.get("sector", "")
    industry = company_info.get("industry", "")
    market_segment = (
        f"{sector}/{industry}" if sector and industry else sector or industry
    )

    # Market cap in billions
    market_cap = company_info.get("market_cap", 0)
    market_cap_b = market_cap / 1_000_000_000 if market_cap else None

    # Get earnings data
    eps_data = analyst_estimates.get("eps", [])
    revenue_data = analyst_estimates.get("revenue", [])

    # Determine which quarter to analyze
    if target_quarter is None:
        # Default: use current quarter (latest unreported)
        target_quarter = find_current_quarter(eps_data)
        if not target_quarter:
            print(
                "Warning: Could not determine current quarter, using latest reported quarter"
            )
            latest_eps = find_latest_reported_quarter(eps_data)
            target_quarter = latest_eps.get("label") if latest_eps else None

    if not target_quarter:
        print("Error: No valid quarter found")
        return None

    # Get data for target quarter
    quarter_eps = find_quarter_data(eps_data, target_quarter, "eps")
    quarter_revenue = find_quarter_data(revenue_data, target_quarter, "revenue")

    # Determine current year from target quarter
    current_year, _ = parse_quarter_label(target_quarter)

    # Calculate full year revenue metrics
    full_year_estimate = None
    full_year_last_year = None
    full_year_two_years_ago = None

    if current_year:
        # Get full year estimate for current year
        full_year_estimate = get_full_year_revenue_estimate(revenue_data, current_year)

        # Get actual revenues from prior years
        full_year_last_year = get_annual_revenue_actual(json_data, current_year - 1)
        full_year_two_years_ago = get_annual_revenue_actual(json_data, current_year - 2)

    # Calculate annual revenue YoY percentages
    revenu_y_yoy_last_year = ""
    revenu_y_yoy_this_year = ""

    if full_year_last_year and full_year_two_years_ago and full_year_two_years_ago > 0:
        yoy_last = calculate_yoy_percentage(full_year_last_year, full_year_two_years_ago)
        revenu_y_yoy_last_year = f"{yoy_last:.2f}" if yoy_last is not None else ""

    if full_year_estimate and full_year_last_year and full_year_last_year > 0:
        yoy_this = calculate_yoy_percentage(full_year_estimate, full_year_last_year)
        revenu_y_yoy_this_year = f"{yoy_this:.2f}" if yoy_this is not None else ""

    # Initialize row with empty values
    row = {
        "ticker": ticker,
        "EPS Q estimate": "",
        "EPS Q actual": "",
        "Revenue Q estimate": "",
        "revenue Q actual": "",
        "EPS same Q actual last year": "",
        "Revenue same Q actual last year": "",
        "Revenue full Y estimate": f"{full_year_estimate/1_000_000_000:.2f}" if full_year_estimate else "",
        "Revenue full Y last year actual": f"{full_year_last_year/1_000_000_000:.2f}" if full_year_last_year else "",
        "revenue full Y actual two year ago": f"{full_year_two_years_ago/1_000_000_000:.2f}" if full_year_two_years_ago else "",
        "EPS beat %": "",
        "Revenue Q Beat %": "",
        "EPS actuall YoY %": "",
        "Revenue actual YoY %": "",
        "Revenue last Q actual YoY %": "",
        "Revenu Y YoY last year": revenu_y_yoy_last_year,
        "Revenu Y YoY this year": revenu_y_yoy_this_year,
    }

    # Fill in EPS data
    if quarter_eps:
        eps_estimate = quarter_eps.get("eps_estimate")
        eps_actual = quarter_eps.get("eps_actual")

        # Check if eps_actual is NaN
        if (
            eps_actual is not None
            and isinstance(eps_actual, float)
            and str(eps_actual) == "nan"
        ):
            eps_actual = None

        row["EPS Q estimate"] = f"{eps_estimate:.2f}" if eps_estimate else ""
        row["EPS Q actual"] = f"{eps_actual:.2f}" if eps_actual else ""

        # Calculate EPS beat % (only if actual is available)
        if eps_estimate and eps_actual and eps_estimate > 0:
            eps_beat_pct = ((eps_actual - eps_estimate) / eps_estimate) * 100
            row["EPS beat %"] = f"{eps_beat_pct:.2f}"

        # Find prior year EPS
        prior_year_eps = find_prior_year_eps(eps_data, target_quarter)

        if prior_year_eps and prior_year_eps.get("eps_actual"):
            prior_eps = prior_year_eps.get("eps_actual")
            row["EPS same Q actual last year"] = f"{prior_eps:.2f}"

            # Calculate EPS actual YoY % - ONLY if we have actual data for current quarter
            # This field should be empty for unreported quarters
            if eps_actual and prior_eps and prior_eps > 0:
                eps_yoy = calculate_yoy_percentage(eps_actual, prior_eps)
                row["EPS actuall YoY %"] = f"{eps_yoy:.2f}" if eps_yoy is not None else ""

    # Fill in Revenue data
    if quarter_revenue:
        revenue_estimate = quarter_revenue.get("revenue_estimate")
        revenue_actual = quarter_revenue.get("revenue_actual")

        # Check if revenue_actual is NaN
        if (
            revenue_actual is not None
            and isinstance(revenue_actual, float)
            and str(revenue_actual) == "nan"
        ):
            revenue_actual = None

        # Convert to billions
        row["Revenue Q estimate"] = (
            f"{revenue_estimate/1_000_000_000:.2f}" if revenue_estimate else ""
        )
        row["revenue Q actual"] = (
            f"{revenue_actual/1_000_000_000:.2f}" if revenue_actual else ""
        )

        # Calculate Revenue beat % (only if actual is available)
        if revenue_estimate and revenue_actual and revenue_estimate > 0:
            revenue_beat_pct = (
                (revenue_actual - revenue_estimate) / revenue_estimate
            ) * 100
            row["Revenue Q Beat %"] = f"{revenue_beat_pct:.2f}"

        # Find prior year revenue
        prior_year_revenue = find_prior_year_revenue(revenue_data, target_quarter)

        if prior_year_revenue and prior_year_revenue.get("revenue_actual"):
            prior_rev = prior_year_revenue.get("revenue_actual")
            row["Revenue same Q actual last year"] = f"{prior_rev/1_000_000_000:.2f}"

            # Calculate Revenue actual YoY % - ONLY if we have actual data for current quarter
            # This field should be empty for unreported quarters
            if revenue_actual and prior_rev and prior_rev > 0:
                rev_yoy = calculate_yoy_percentage(revenue_actual, prior_rev)
                row["Revenue actual YoY %"] = (
                    f"{rev_yoy:.2f}" if rev_yoy is not None else ""
                )

        # Find prior quarter revenue for sequential growth
        prior_quarter_revenue = find_prior_quarter_revenue(revenue_data, target_quarter)

        if prior_quarter_revenue and prior_quarter_revenue.get("revenue_actual"):
            prior_q_rev = prior_quarter_revenue.get("revenue_actual")

            # Calculate sequential YoY % (comparing to same quarter last year of prior quarter)
            prior_q_label = prior_quarter_revenue.get("label")
            prior_q_year_revenue = find_prior_year_revenue(revenue_data, prior_q_label)

            if prior_q_year_revenue and prior_q_year_revenue.get("revenue_actual"):
                prior_q_prior_year = prior_q_year_revenue.get("revenue_actual")
                if prior_q_prior_year and prior_q_prior_year > 0:
                    last_q_yoy = calculate_yoy_percentage(
                        prior_q_rev, prior_q_prior_year
                    )
                    row["Revenue last Q actual YoY %"] = (
                        f"{last_q_yoy:.2f}" if last_q_yoy is not None else ""
                    )

    return row


def generate_csv(input_file, output_file=None, target_quarter=None):
    """Generate CSV file from JSON data

    Args:
        input_file: Path to input JSON file
        output_file: Path to output CSV file (optional)
        target_quarter: Quarter label to analyze (e.g., '2025Q3'). If None, uses current quarter.

    Returns:
        0 on success, 1 on error
    """
    input_path = Path(input_file)

    if not input_path.exists():
        print(f"Error: Input file '{input_file}' not found")
        return 1

    # Read JSON data
    with open(input_path, "r") as f:
        json_data = json.load(f)

    # Generate row
    row = generate_csv_row(json_data, target_quarter=target_quarter)

    if row is None:
        print("Error: Failed to generate CSV row")
        return 1

    # Determine output filename
    if output_file is None:
        quarter_suffix = f"_{row['quarter']}" if row.get("quarter") else ""
        output_file = input_path.stem + quarter_suffix + "_analysis.csv"

    output_path = Path(output_file)

    # Write CSV
    fieldnames = [
        "ticker",
        "EPS Q estimate",
        "EPS Q actual",
        "Revenue Q estimate",
        "revenue Q actual",
        "EPS same Q actual last year",
        "Revenue same Q actual last year",
        "Revenue full Y estimate",
        "Revenue full Y last year actual",
        "revenue full Y actual two year ago",
        "EPS beat %",
        "Revenue Q Beat %",
        "EPS actuall YoY %",
        "Revenue actual YoY %",
        "Revenue last Q actual YoY %",
        "Revenu Y YoY last year",
        "Revenu Y YoY this year",
    ]

    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerow(row)

    print(f"✓ Generated CSV file: {output_path}")
    print(f"  Ticker: {row['ticker']}")
    print(f"  EPS: {row['EPS Q actual']} (estimate: {row['EPS Q estimate']})")
    print(
        f"  Revenue: {row['revenue Q actual']}B (estimate: {row['Revenue Q estimate']}B)"
    )
    print(f"  Revenu Y YoY last year: {row['Revenu Y YoY last year']}%")
    print(f"  Revenu Y YoY this year: {row['Revenu Y YoY this year']}%")

    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Generate CSV file for earnings analysis from financial data JSON files.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Analyze current quarter (latest unreported)
  python generate_analysis_csv.py aapl.json

  # Analyze specific quarter for validation
  python generate_analysis_csv.py aapl.json --quarter 2025Q2

  # Specify output file
  python generate_analysis_csv.py aapl.json aapl_analysis.csv --quarter 2025Q2
        """,
    )

    parser.add_argument("input_json", help="Input JSON file with financial data")
    parser.add_argument("output_csv", nargs="?", help="Output CSV file (optional)")
    parser.add_argument(
        "--quarter",
        "-q",
        help="Quarter to analyze (e.g., 2025Q3). Default: current quarter (latest unreported)",
    )

    args = parser.parse_args()

    return generate_csv(args.input_json, args.output_csv, args.quarter)


if __name__ == "__main__":
    sys.exit(main())
