#!/usr/bin/env python3
"""
Test individual TradingView fields to find what's available.
"""

import requests
import json

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


# Test fields related to annual and historical data
test_fields = [
    # Annual fields
    "earnings_per_share_fy",
    "revenue_fy",
    "total_revenue",
    "net_income",
    "net_income_fy",

    # Diluted EPS
    "earnings_per_share_diluted_fy",
    "earnings_per_share_basic_fy",

    # Previous periods
    "earnings_per_share_prev_fq",
    "revenue_prev_fq",

    # Year over year growth
    "earnings_per_share_yoy_growth_fq",
    "revenue_yoy_growth_fq",
    "earnings_per_share_yoy",
    "revenue_yoy",

    # TTM (Trailing Twelve Months)
    "earnings_per_share_ttm",
    "revenue_ttm",
    "total_revenue_ttm",

    # Diluted
    "earnings_per_share_diluted_fq",
    "earnings_per_share_basic_fq",
]

print("Testing TradingView Scanner API Fields")
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
        working_fields.append(field)

print("\n" + "="*80)
print(f"Working fields: {len(working_fields)}/{len(test_fields)}")
print("\nWorking field list:")
for field in working_fields:
    print(f"  - {field}")
