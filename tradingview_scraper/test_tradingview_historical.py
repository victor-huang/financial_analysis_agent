#!/usr/bin/env python3
"""
Test for multi-year historical data fields in TradingView.
"""

import requests

def test_single_field(field_name, ticker="NASDAQ:MU"):
    """Test a single field."""
    url = "https://scanner.tradingview.com/america/scan"

    headers = {
        "accept": "text/plain, */*; q=0.01",
        "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
        "origin": "https://www.tradingview.com",
        "referer": "https://www.tradingview.com/",
        "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
    }

    payload = {
        "symbols": {
            "tickers": [ticker]
        },
        "columns": ["name", field_name]
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if "data" in data and len(data["data"]) > 0:
                values = data["data"][0].get("d", [])
                if len(values) > 1:
                    return True, values[1]
        return False, None
    except Exception:
        return False, None


# Test fields for historical years
# Trying different naming conventions
test_fields = [
    # FY-1, FY-2, etc. (previous years)
    "earnings_per_share_fy_1",
    "earnings_per_share_fy_2",
    "earnings_per_share_fy_3",
    "earnings_per_share_fy_4",
    "earnings_per_share_fy_5",

    "total_revenue_fy_1",
    "total_revenue_fy_2",

    # Previous year
    "earnings_per_share_prev_fy",
    "total_revenue_prev_fy",
    "revenue_prev_fy",

    # Fiscal year with numbers
    "earnings_per_share_fy1",
    "earnings_per_share_fy2",
    "total_revenue_fy1",
    "total_revenue_fy2",

    # Year ago
    "earnings_per_share_1y",
    "total_revenue_1y",

    # Quarterly history
    "earnings_per_share_fq1",
    "earnings_per_share_fq2",
    "earnings_per_share_fq3",
    "earnings_per_share_fq4",

    "revenue_fq1",
    "revenue_fq2",
    "revenue_fq3",
    "revenue_fq4",

    # Same quarter last year (SQ = same quarter)
    "earnings_per_share_sq",
    "revenue_sq",

    # Five quarters ago (same quarter last year + 1 quarter)
    "earnings_per_share_fq_5",
    "revenue_fq_5",
]

print("Testing Historical Data Fields")
print("="*80)
print(f"{'Field Name':<45} {'Status':<10} {'Value'}")
print("-"*80)

working_fields = []
for field in test_fields:
    works, value = test_single_field(field)
    status = "✓ WORKS" if works else "✗ FAILS"
    value_str = str(value) if value is not None else "N/A"
    print(f"{field:<45} {status:<10} {value_str}")

    if works:
        working_fields.append((field, value))

print("\n" + "="*80)
print(f"Working fields: {len(working_fields)}/{len(test_fields)}")

if working_fields:
    print("\nWorking fields with values:")
    for field, value in working_fields:
        print(f"  - {field}: {value}")
else:
    print("\nNo historical fields found.")
    print("\nConclusion: TradingView Scanner API appears to only provide:")
    print("  - Current fiscal year (FY) data")
    print("  - Current quarter (FQ) data")
    print("  - Trailing twelve months (TTM) data")
    print("  - Does NOT provide multi-year historical data")
