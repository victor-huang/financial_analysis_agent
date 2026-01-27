#!/usr/bin/env python3
"""
Test script to explore available TradingView scanner API fields for historical data.
"""

import requests
import json


def test_tradingview_fields(ticker="NASDAQ:MU"):
    """
    Test TradingView scanner API with expanded field list to find historical data.
    """
    url = "https://scanner.tradingview.com/america/scan"

    headers = {
        "accept": "text/plain, */*; q=0.01",
        "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
        "origin": "https://www.tradingview.com",
        "referer": "https://www.tradingview.com/",
        "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    }

    # Test for annual (FY = fiscal year) fields
    test_columns = [
        "name",
        # Current quarter
        "earnings_per_share_fq",
        "revenue_fq",
        # Try annual fields
        "earnings_per_share_fy",
        "revenue_fy",
        "total_revenue",
        "net_income",
    ]

    payload = {"symbols": {"tickers": [ticker]}, "columns": test_columns}

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        response.raise_for_status()
        data = response.json()

        print(f"Testing ticker: {ticker}")
        print(f"Number of columns requested: {len(test_columns)}")
        print("\n" + "=" * 80)

        if "data" in data and len(data["data"]) > 0:
            item = data["data"][0]
            values = item.get("d", [])

            print(f"\nReceived {len(values)} values")
            print("\nField Name → Value")
            print("-" * 80)

            for i, (col, val) in enumerate(zip(test_columns, values)):
                if val is not None:
                    print(f"{i:3d}. {col:40s} → {val}")
                else:
                    print(f"{i:3d}. {col:40s} → (null)")
        else:
            print("No data returned")

        # Print raw response for debugging
        print("\n" + "=" * 80)
        print("Raw Response:")
        print(json.dumps(data, indent=2))

    except requests.exceptions.RequestException as e:
        print(f"Request error: {e}")
    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    test_tradingview_fields()
