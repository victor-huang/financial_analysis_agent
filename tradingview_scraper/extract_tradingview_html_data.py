#!/usr/bin/env python3
"""
Extract financial data directly from TradingView HTML page source.
Since there are no obvious XHR requests, the data is likely embedded in the HTML.
"""

import requests
import json
import re
from typing import Dict, List, Optional
from bs4 import BeautifulSoup


def fetch_tradingview_page(ticker="MU", exchange="NASDAQ", page_type="forecast"):
    """
    Fetch TradingView page HTML.

    Args:
        ticker: Stock ticker
        exchange: Exchange name
        page_type: "forecast" or "financials-overview"

    Returns:
        HTML content as string
    """
    url = f"https://www.tradingview.com/symbols/{exchange}-{ticker}/{page_type}/"

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
    }

    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        return response.text
    except Exception as e:
        print(f"Error fetching page: {e}")
        return None


def extract_json_from_scripts(html: str) -> List[Dict]:
    """
    Extract all JSON objects from script tags.
    """
    soup = BeautifulSoup(html, 'html.parser')
    json_objects = []

    # Find all script tags
    scripts = soup.find_all('script')

    print(f"Found {len(scripts)} script tags")

    for i, script in enumerate(scripts):
        script_content = script.string
        if not script_content:
            continue

        # Look for JSON-like structures
        # Pattern 1: window.variable = {...}
        matches = re.findall(r'window\.\w+\s*=\s*(\{.*?\});', script_content, re.DOTALL)
        for match in matches:
            try:
                data = json.loads(match)
                if data:  # Not empty
                    json_objects.append(("window.variable", data))
            except:
                pass

        # Pattern 2: Pure JSON objects
        matches = re.findall(r'(\{["\w]+:[^<>]*\})', script_content)
        for match in matches:
            try:
                data = json.loads(match)
                if data:
                    json_objects.append(("inline_json", data))
            except:
                pass

    return json_objects


def search_for_financial_keywords(html: str) -> Dict[str, List[str]]:
    """
    Search for financial data patterns in HTML.
    """
    keywords = {
        "revenue": [],
        "earnings": [],
        "eps": [],
        "fiscal": [],
        "annual": [],
        "quarterly": [],
        "forecast": [],
        "estimate": []
    }

    for keyword in keywords.keys():
        # Find all occurrences with context
        pattern = rf'.{{0,100}}{keyword}.{{0,100}}'
        matches = re.findall(pattern, html, re.IGNORECASE)
        keywords[keyword] = matches[:10]  # Keep first 10 matches

    return keywords


def extract_from_json_ld(html: str) -> Optional[Dict]:
    """
    Extract data from JSON-LD schema tags.
    """
    soup = BeautifulSoup(html, 'html.parser')
    json_ld_scripts = soup.find_all('script', type='application/ld+json')

    results = []
    for script in json_ld_scripts:
        try:
            data = json.loads(script.string)
            results.append(data)
        except:
            pass

    return results


def extract_inline_data_attributes(html: str) -> Dict[str, str]:
    """
    Extract data from HTML data-* attributes.
    """
    soup = BeautifulSoup(html, 'html.parser')

    # Look for elements with data attributes
    elements_with_data = soup.find_all(attrs={"data-symbol": True})
    elements_with_data += soup.find_all(attrs={"data-financials": True})
    elements_with_data += soup.find_all(attrs={"data-chart": True})
    elements_with_data += soup.find_all(attrs={"data-forecast": True})

    data_attrs = {}
    for elem in elements_with_data:
        for attr, value in elem.attrs.items():
            if attr.startswith('data-'):
                data_attrs[attr] = value

    return data_attrs


def find_embedded_arrays(html: str) -> Dict[str, List]:
    """
    Find arrays that might contain financial data.
    """
    arrays = {}

    # Look for array patterns: [number, number, number]
    # Focusing on arrays with large numbers (likely revenue) or decimal numbers (likely EPS)

    # Pattern for arrays of large numbers (billions)
    pattern_billions = r'\[(\d{10,12}(?:,\s*\d{10,12})+)\]'
    matches = re.findall(pattern_billions, html)
    if matches:
        arrays['large_numbers'] = matches[:5]

    # Pattern for arrays of decimal numbers (EPS)
    pattern_decimals = r'\[(-?\d+\.\d+(?:,\s*-?\d+\.\d+)+)\]'
    matches = re.findall(pattern_decimals, html)
    if matches:
        arrays['decimal_numbers'] = matches[:10]

    # Pattern for labeled arrays
    pattern_labeled = r'["\']?(?:revenue|earnings|eps)["\']?\s*:\s*\[([^\]]+)\]'
    matches = re.findall(pattern_labeled, html, re.IGNORECASE)
    if matches:
        arrays['labeled_arrays'] = matches[:10]

    return arrays


def analyze_page_structure(html: str) -> Dict:
    """
    Analyze the overall structure to understand how data is loaded.
    """
    soup = BeautifulSoup(html, 'html.parser')

    analysis = {
        "has_react_root": bool(soup.find(id="__NEXT_DATA__")),
        "has_vue_app": bool(soup.find(attrs={"data-v-app": True})),
        "script_count": len(soup.find_all('script')),
        "external_scripts": [s.get('src') for s in soup.find_all('script', src=True)],
        "websocket_refs": [],
        "api_refs": []
    }

    # Look for WebSocket or API references in the HTML
    if 'websocket' in html.lower() or 'wss://' in html.lower():
        matches = re.findall(r'wss://[^\s"\'<>]+', html)
        analysis['websocket_refs'] = matches

    if 'api' in html.lower():
        matches = re.findall(r'https://[^\s"\'<>]*api[^\s"\'<>]*', html, re.IGNORECASE)
        analysis['api_refs'] = matches[:10]

    return analysis


def main():
    ticker = "MU"
    exchange = "NASDAQ"

    print("="*80)
    print(f"Extracting TradingView Financial Data from HTML")
    print(f"Ticker: {exchange}:{ticker}")
    print("="*80)

    # Try both page types
    for page_type in ["forecast", "financials-overview"]:
        print(f"\n{'='*80}")
        print(f"Analyzing {page_type} page")
        print('='*80)

        html = fetch_tradingview_page(ticker, exchange, page_type)

        if not html:
            print(f"✗ Failed to fetch {page_type} page")
            continue

        print(f"✓ Fetched HTML ({len(html):,} characters)")

        # 1. Analyze page structure
        print("\n1. Page Structure Analysis:")
        print("-"*80)
        structure = analyze_page_structure(html)
        print(json.dumps(structure, indent=2))

        # 2. Look for JSON-LD
        print("\n2. JSON-LD Schema Data:")
        print("-"*80)
        json_ld = extract_from_json_ld(html)
        if json_ld:
            print(f"✓ Found {len(json_ld)} JSON-LD objects")
            for i, data in enumerate(json_ld):
                print(f"\nJSON-LD {i+1}:")
                print(json.dumps(data, indent=2)[:500])
        else:
            print("✗ No JSON-LD found")

        # 3. Extract JSON from scripts
        print("\n3. JSON Objects in Script Tags:")
        print("-"*80)
        json_objects = extract_json_from_scripts(html)
        print(f"✓ Found {len(json_objects)} JSON objects")

        # Look for financial data in these objects
        for source, data in json_objects[:5]:
            if isinstance(data, dict):
                # Check if it has financial keywords
                data_str = json.dumps(data).lower()
                if any(word in data_str for word in ['revenue', 'earning', 'eps', 'fiscal', 'quarter']):
                    print(f"\n✓ Found potential financial data in {source}:")
                    print(json.dumps(data, indent=2)[:800])

        # 4. Data attributes
        print("\n4. HTML Data Attributes:")
        print("-"*80)
        data_attrs = extract_inline_data_attributes(html)
        if data_attrs:
            print(f"✓ Found {len(data_attrs)} data attributes")
            for attr, value in list(data_attrs.items())[:10]:
                print(f"  {attr}: {value[:100]}")
        else:
            print("✗ No relevant data attributes found")

        # 5. Search for embedded arrays
        print("\n5. Embedded Number Arrays:")
        print("-"*80)
        arrays = find_embedded_arrays(html)
        for array_type, matches in arrays.items():
            print(f"\n{array_type}:")
            for match in matches[:3]:
                print(f"  [{match}]")

        # 6. Keyword search
        print("\n6. Financial Keyword Context:")
        print("-"*80)
        keywords = search_for_financial_keywords(html)
        for keyword, contexts in keywords.items():
            if contexts:
                print(f"\n{keyword.upper()} ({len(contexts)} occurrences):")
                print(f"  Example: ...{contexts[0]}...")

        # 7. Save raw HTML for manual inspection
        filename = f"tradingview_{page_type}_{ticker}.html"
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(html)
        print(f"\n✓ Saved raw HTML to: {filename}")
        print(f"  You can inspect it manually for data patterns")


if __name__ == "__main__":
    main()
