#!/usr/bin/env python3
"""
Parse TradingView chart data from rendered DOM.
The data is in the bar chart heights and labels.
"""

import re
import json
from bs4 import BeautifulSoup
from typing import Dict, List, Optional, Tuple


def parse_chart_from_html(html_file: str) -> Dict:
    """
    Parse chart data from rendered TradingView HTML.

    Args:
        html_file: Path to the rendered HTML file

    Returns:
        Dictionary with extracted financial data
    """
    with open(html_file, 'r', encoding='utf-8') as f:
        html = f.read()

    soup = BeautifulSoup(html, 'html.parser')

    # Find the chart container
    chart_container = soup.find('div', class_=re.compile(r'chart-.*'))

    if not chart_container:
        print("✗ Chart container not found")
        return {}

    print("✓ Found chart container")

    # Extract quarter labels (x-axis)
    quarters = []
    quarter_elements = soup.find_all('div', class_=re.compile(r'horizontalScaleValue'))
    for elem in quarter_elements:
        quarter_text = elem.get_text(strip=True)
        if quarter_text:
            quarters.append(quarter_text)

    print(f"✓ Found {len(quarters)} quarters: {quarters}")

    # Extract scale values (y-axis) - these are the EPS values
    scale_values = []
    scale_elements = soup.find_all('div', class_=re.compile(r'verticalScaleValue'))
    for elem in scale_elements:
        value_text = elem.get_text(strip=True).replace('\u202a', '').replace('\u202c', '')  # Remove unicode markers
        try:
            value = float(value_text)
            scale_values.append(value)
        except ValueError:
            continue

    scale_values.sort()  # Sort to get min to max
    print(f"✓ Found scale values: {scale_values}")

    if not scale_values:
        print("✗ No scale values found")
        return {}

    max_value = max(scale_values)
    min_value = min(scale_values)

    # Extract bar data (each column represents a quarter)
    columns = soup.find_all('div', class_=re.compile(r'^column-[A-Za-z0-9]+$'))

    eps_data = []

    for i, column in enumerate(columns):
        # Find bars in this column
        bars = column.find_all('div', class_=re.compile(r'bar-'))

        reported_eps = None
        estimate_eps = None

        for bar in bars:
            style = bar.get('style', '')

            # Extract height percentage
            height_match = re.search(r'height:\s*max\(([0-9.]+)%', style)
            if not height_match:
                continue

            height_percent = float(height_match.group(1))

            # Calculate actual EPS value from percentage
            eps_value = (height_percent / 100.0) * (max_value - min_value) + min_value

            # Check if it's reported or estimate based on color
            if '--inner-bar-color: #3179F5' in style or '#3179F5' in style:
                # Blue color = Reported
                reported_eps = round(eps_value, 2)
            elif '--inner-bar-color: #EBEBEB' in style or 'EBEBEB' in style:
                # Gray color = Estimate
                estimate_eps = round(eps_value, 2)

        quarter = quarters[i] if i < len(quarters) else f"Q{i+1}"

        eps_data.append({
            "quarter": quarter,
            "reported_eps": reported_eps,
            "estimate_eps": estimate_eps
        })

    return {
        "quarters": quarters,
        "scale": {"min": min_value, "max": max_value},
        "eps_data": eps_data
    }


def parse_revenue_from_html(html_file: str) -> Dict:
    """
    Similar to EPS parsing, but for revenue chart.
    Revenue uses the same structure but different scale values.
    """
    # The logic is similar, but we need to find the revenue section
    with open(html_file, 'r', encoding='utf-8') as f:
        html = f.read()

    soup = BeautifulSoup(html, 'html.parser')

    # Look for revenue-specific section
    # This will depend on the exact page structure
    # For now, returning placeholder

    return {"message": "Revenue parsing needs section identification"}


def main():
    """Parse the rendered HTML files."""
    print("="*80)
    print("TradingView Chart Data Parser")
    print("="*80)

    # Parse EPS data from forecast page
    print("\nParsing EPS data from rendered HTML...")
    print("-"*80)

    eps_data = parse_chart_from_html("tradingview_rendered_MU.html")

    if eps_data:
        print("\n✓ Successfully parsed EPS data!")
        print(json.dumps(eps_data, indent=2))

        # Display as table
        print("\n" + "="*80)
        print("EPS DATA TABLE")
        print("="*80)
        print(f"{'Quarter':<15} {'Reported EPS':>15} {'Estimate EPS':>15}")
        print("-"*50)

        for item in eps_data.get("eps_data", []):
            quarter = item['quarter']
            reported = item['reported_eps'] if item['reported_eps'] else "N/A"
            estimate = item['estimate_eps'] if item['estimate_eps'] else "N/A"
            print(f"{quarter:<15} {str(reported):>15} {str(estimate):>15}")

        # Save to JSON
        with open("tradingview_eps_data_MU.json", "w") as f:
            json.dump(eps_data, f, indent=2)
        print("\n✓ Saved to: tradingview_eps_data_MU.json")

    else:
        print("\n✗ Failed to parse EPS data")

    # Try financials page too
    print("\n" + "="*80)
    print("Parsing financial overview page...")
    print("-"*80)

    financials_eps = parse_chart_from_html("tradingview_financials_rendered_MU.html")

    if financials_eps:
        print("\n✓ Successfully parsed data from financials page!")
        print(json.dumps(financials_eps, indent=2)[:1000])


if __name__ == "__main__":
    main()
