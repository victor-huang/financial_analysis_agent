#!/usr/bin/env python3
"""
Extract financial data from TradingView financials-overview and forecast pages.
"""

import requests
import json
import re
from bs4 import BeautifulSoup

def extract_embedded_data(ticker="MU", exchange="NASDAQ"):
    """
    Extract embedded JSON data from TradingView pages.
    """
    pages = {
        "forecast": f"https://www.tradingview.com/symbols/{exchange}-{ticker}/forecast/",
        "financials": f"https://www.tradingview.com/symbols/{exchange}-{ticker}/financials-overview/",
        "financials-full": f"https://www.tradingview.com/symbols/{exchange}-{ticker}/financials-full/",
    }

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }

    for page_name, url in pages.items():
        print(f"\n{'='*80}")
        print(f"Analyzing: {page_name}")
        print(f"URL: {url}")
        print('='*80)

        try:
            response = requests.get(url, headers=headers, timeout=15)

            if response.status_code != 200:
                print(f"✗ Status {response.status_code}")
                continue

            print(f"✓ Page loaded successfully")

            html = response.text

            # Look for various data embedding patterns
            patterns = [
                (r'window\.__INIT_DATA__\s*=\s*(\{.*?\});', 'window.__INIT_DATA__'),
                (r'window\.initData\s*=\s*(\{.*?\});', 'window.initData'),
                (r'"financialData"\s*:\s*(\{.*?\}),', 'financialData'),
                (r'"revenue"\s*:\s*(\[.*?\])', 'revenue array'),
                (r'"earnings"\s*:\s*(\[.*?\])', 'earnings array'),
                (r'"estimates"\s*:\s*(\{.*?\})', 'estimates object'),
            ]

            found_data = False

            for pattern, description in patterns:
                matches = re.findall(pattern, html, re.DOTALL)
                if matches:
                    print(f"\n✓ Found {description}")
                    for i, match in enumerate(matches[:3]):  # Show first 3 matches
                        try:
                            # Try to parse as JSON
                            data = json.loads(match)
                            print(f"\n{description} - Match {i+1}:")
                            print(json.dumps(data, indent=2)[:1500])
                            found_data = True

                            # Look specifically for revenue/earnings arrays
                            if isinstance(data, dict):
                                for key in ['revenue', 'earnings', 'financials', 'data', 'annual', 'quarterly']:
                                    if key in data:
                                        print(f"\n>>> Key '{key}' found in data!")
                                        print(json.dumps(data[key], indent=2)[:800])

                        except json.JSONDecodeError:
                            print(f"Could not parse as JSON: {match[:200]}...")

            # Also search for specific financial keywords
            financial_keywords = ['annual_revenue', 'quarterly_revenue', 'annual_eps', 'quarterly_eps', 'fiscal_year']
            for keyword in financial_keywords:
                if keyword in html.lower():
                    print(f"\n✓ Found keyword: {keyword}")
                    # Find context around the keyword
                    idx = html.lower().find(keyword)
                    context = html[max(0, idx-100):min(len(html), idx+200)]
                    print(f"Context: ...{context}...")

            if not found_data:
                print("\n✗ No structured financial data found in HTML")
                print("Trying to find any JSON-like structures...")

                # Find all potential JSON objects
                json_objects = re.findall(r'\{["\w]+:[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', html)
                if json_objects:
                    print(f"Found {len(json_objects)} potential JSON objects")
                    for obj in json_objects[:5]:
                        if any(word in obj.lower() for word in ['revenue', 'earning', 'fiscal', 'quarter', 'annual']):
                            print(f"\nPotential match: {obj[:300]}...")

        except Exception as e:
            print(f"✗ Error: {e}")

    return None


def check_alternative_endpoints(ticker="MU", exchange="NASDAQ"):
    """
    Check if there are alternative API endpoints for financial data.
    """
    symbol = f"{exchange}:{ticker}"

    # Try the pattern used by other financial sites
    endpoints = [
        f"https://www.tradingview.com/chart-data/financials/{symbol}/",
        f"https://www.tradingview.com/api/v1/symbols/{symbol}/financials/",
        f"https://www.tradingview.com/stock-data/{symbol}/",
    ]

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Accept": "application/json, */*",
        "Referer": f"https://www.tradingview.com/symbols/{exchange}-{ticker}/forecast/",
    }

    print(f"\n{'='*80}")
    print("Testing alternative API endpoints...")
    print('='*80)

    for url in endpoints:
        try:
            print(f"\n{url}")
            response = requests.get(url, headers=headers, timeout=10)
            print(f"Status: {response.status_code}")

            if response.status_code == 200:
                print("✓ SUCCESS!")
                try:
                    data = response.json()
                    print(json.dumps(data, indent=2)[:1000])
                except:
                    print(f"Response preview: {response.text[:500]}")

        except Exception as e:
            print(f"Error: {str(e)[:100]}")


def main():
    print("TradingView Financial Data Extraction")
    print("="*80)

    extract_embedded_data("MU", "NASDAQ")
    check_alternative_endpoints("MU", "NASDAQ")

    print("\n" + "="*80)
    print("\nConclusion:")
    print("If no API endpoints found, the data is likely:")
    print("1. Embedded in JavaScript bundles (requires JS execution)")
    print("2. Loaded via WebSocket after page load")
    print("3. Behind authentication/session requirements")
    print("\nRecommendation: Use browser DevTools Network tab to capture actual requests")


if __name__ == "__main__":
    main()
