#!/usr/bin/env python3
"""
Inspect TradingView forecast page to find the API endpoints used for historical data.
This script will try to make similar requests to what the browser makes.
"""

import requests
import json
import re
from urllib.parse import urlparse, parse_qs

def test_symbol_overview_endpoint(ticker="MU", exchange="NASDAQ"):
    """
    Test if TradingView has a symbol-overview or financials endpoint.
    """
    symbol = f"{exchange}:{ticker}"

    # Try various potential endpoint patterns
    potential_endpoints = [
        f"https://symbol-overview.tradingview.com/v1/symbols/{symbol}",
        f"https://symbol-overview.tradingview.com/symbols/{symbol}/financials",
        f"https://symbol-overview.tradingview.com/symbols/{symbol}/forecast",
        f"https://financials.tradingview.com/v1/symbols/{symbol}",
        f"https://api.tradingview.com/v1/symbols/{symbol}/financials",
        f"https://scanner.tradingview.com/symbol",
        f"https://symbol-search.tradingview.com/symbol_search/v3/",
    ]

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Accept": "application/json, text/plain, */*",
        "Referer": f"https://www.tradingview.com/symbols/{exchange}-{ticker}/forecast/",
        "Origin": "https://www.tradingview.com",
    }

    print("Testing potential API endpoints...")
    print("="*80)

    for url in potential_endpoints:
        try:
            response = requests.get(url, headers=headers, timeout=10)
            print(f"\n{url}")
            print(f"Status: {response.status_code}")

            if response.status_code == 200:
                print(f"✓ SUCCESS!")
                print(f"Content preview: {response.text[:500]}")
                return response.json() if response.text else None
            elif response.status_code == 404:
                print(f"✗ Not Found")
            elif response.status_code == 403:
                print(f"✗ Forbidden")
            else:
                print(f"✗ Status: {response.status_code}")

        except requests.exceptions.RequestException as e:
            print(f"✗ Request failed: {str(e)[:100]}")
        except Exception as e:
            print(f"✗ Error: {str(e)[:100]}")

    return None


def test_screener_facade(ticker="MU", exchange="NASDAQ"):
    """
    Test the screener-facade endpoint which might provide financial data.
    """
    symbol = f"{exchange}:{ticker}"

    url = "https://screener-facade.tradingview.com/screener-facade"

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Referer": f"https://www.tradingview.com/symbols/{exchange}-{ticker}/forecast/",
        "Origin": "https://www.tradingview.com",
    }

    # Try to request financial data
    payload = {
        "symbols": [symbol],
        "fields": [
            "revenue_fq",
            "earnings_per_share_fq",
            "total_revenue",
            "earnings_per_share_fy"
        ]
    }

    print("\n" + "="*80)
    print("Testing screener-facade endpoint...")
    print(f"URL: {url}")

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        print(f"Status: {response.status_code}")

        if response.status_code == 200:
            print("✓ SUCCESS!")
            data = response.json()
            print(json.dumps(data, indent=2)[:1000])
            return data
        else:
            print(f"Response: {response.text[:500]}")

    except Exception as e:
        print(f"Error: {e}")

    return None


def test_financials_endpoint(ticker="MU", exchange="NASDAQ"):
    """
    Test various financial data endpoints.
    """
    symbol = f"{exchange}:{ticker}"

    # Common financial data API patterns
    patterns = [
        f"https://www.tradingview.com/symbols/{exchange}-{ticker}/financials-overview/",
        f"https://www.tradingview.com/symbols/{exchange}-{ticker}/financials-statistics/",
        f"https://pine-facade.tradingview.com/pine-facade/translate/{symbol}/",
        f"https://symbol-search.tradingview.com/symbol_info/",
    ]

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Accept": "application/json, text/html, */*",
        "Referer": f"https://www.tradingview.com/symbols/{exchange}-{ticker}/forecast/",
    }

    print("\n" + "="*80)
    print("Testing financial data endpoints...")

    for url in patterns:
        try:
            print(f"\n{url}")
            response = requests.get(url, headers=headers, timeout=10)
            print(f"Status: {response.status_code}")

            if response.status_code == 200:
                print("✓ Response received")
                # Check if it's JSON
                try:
                    data = response.json()
                    print(f"JSON data preview: {json.dumps(data, indent=2)[:500]}")
                except:
                    # It's HTML, look for embedded data
                    if "revenue" in response.text.lower() or "earnings" in response.text.lower():
                        print("✓ Contains revenue/earnings data in HTML")
                        # Try to find embedded JSON
                        json_matches = re.findall(r'window\.__INIT_DATA__\s*=\s*({.*?});', response.text, re.DOTALL)
                        if json_matches:
                            print(f"Found embedded data: {json_matches[0][:200]}...")

        except Exception as e:
            print(f"Error: {str(e)[:100]}")


def main():
    """Main execution."""
    print("TradingView Forecast Page API Investigation")
    print("="*80)
    print("Analyzing: NASDAQ:MU (Micron Technology)")
    print()

    # Test different endpoint patterns
    test_symbol_overview_endpoint()
    test_screener_facade()
    test_financials_endpoint()

    print("\n" + "="*80)
    print("\nNext Steps:")
    print("1. Use browser DevTools Network tab to capture actual requests")
    print("2. Look for XHR/Fetch requests when loading the forecast page")
    print("3. Check for WebSocket messages containing financial data")
    print("4. Inspect page source for window.__INIT_DATA__ or similar embedded data")


if __name__ == "__main__":
    main()
