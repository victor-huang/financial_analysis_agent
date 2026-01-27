#!/usr/bin/env python3
"""
Analyze TradingView JavaScript bundles to find API endpoints or data loading logic.
"""

import requests
import re
import json


def download_and_analyze_bundle(bundle_url):
    """Download and analyze a JavaScript bundle for API endpoints."""
    print(f"\nAnalyzing: {bundle_url.split('/')[-1]}")
    print("-" * 80)

    try:
        response = requests.get(bundle_url, timeout=15)
        response.raise_for_status()
        js_content = response.text

        print(f"✓ Downloaded ({len(js_content):,} characters)")

        # Search for API endpoint patterns
        patterns = {
            "URL patterns": r'https?://[^\s"\'<>]+',
            "API paths": r'["\']/(api|financials|forecast|estimates)[^"\']*["\']',
            "WebSocket messages": r'["\'](?:quote|financial|estimate|forecast)["\']:\s*{',
            "Revenue/EPS fields": r'["\'](?:revenue|eps|earnings)["\']:\s*[{\[]',
        }

        findings = {}

        for pattern_name, pattern in patterns.items():
            matches = re.findall(pattern, js_content, re.IGNORECASE)
            if matches:
                # Remove duplicates and filter relevant ones
                unique_matches = list(set(matches))[:20]
                findings[pattern_name] = unique_matches

        # Print findings
        for pattern_name, matches in findings.items():
            if matches:
                print(f"\n{pattern_name}:")
                for match in matches[:10]:
                    print(f"  - {match}")

        # Search for specific financial data loading functions
        data_loading_patterns = [
            r"function\s+\w*(?:load|fetch|get)(?:Financial|Forecast|Revenue|Earnings)\w*\([^)]*\)\s*{[^}]{0,500}",
            r"(?:revenue|earnings|eps)\s*:\s*function\s*\([^)]*\)\s*{[^}]{0,300}",
        ]

        print("\n\nData Loading Functions:")
        print("-" * 80)

        for pattern in data_loading_patterns:
            matches = re.findall(pattern, js_content, re.IGNORECASE)
            if matches:
                for match in matches[:3]:
                    print(f"\n{match[:300]}...")

        return findings

    except Exception as e:
        print(f"✗ Error: {e}")
        return None


def main():
    """Analyze key TradingView bundles."""
    print("=" * 80)
    print("TradingView JavaScript Bundle Analysis")
    print("=" * 80)

    # Key bundles to analyze
    bundles = [
        "https://static.tradingview.com/static/bundles/forecast.ee81b69f8b31fc12d573.js",
        "https://static.tradingview.com/static/bundles/init-financials-page.1382ae5262fba1fdc340.js",
        "https://static.tradingview.com/static/bundles/category_financials.ab71bd5f4e350704e523.js",
    ]

    all_findings = {}

    for bundle_url in bundles:
        findings = download_and_analyze_bundle(bundle_url)
        if findings:
            bundle_name = bundle_url.split("/")[-1]
            all_findings[bundle_name] = findings

    # Summary
    print("\n\n" + "=" * 80)
    print("SUMMARY - Unique API Endpoints Found")
    print("=" * 80)

    all_urls = set()
    for bundle_findings in all_findings.values():
        if "URL patterns" in bundle_findings:
            all_urls.update(bundle_findings["URL patterns"])

    # Filter for relevant endpoints
    relevant_endpoints = [
        url
        for url in all_urls
        if any(
            keyword in url.lower()
            for keyword in [
                "financial",
                "forecast",
                "revenue",
                "earnings",
                "estimate",
                "scanner",
                "symbol",
                "quote",
                "api",
            ]
        )
        and not any(
            skip in url for skip in [".js", ".css", ".png", ".jpg", ".woff", ".svg"]
        )
    ]

    if relevant_endpoints:
        print("\n✓ Potentially useful endpoints:")
        for endpoint in sorted(relevant_endpoints)[:30]:
            print(f"  - {endpoint}")
    else:
        print("\n✗ No obvious API endpoints found in JavaScript bundles")
        print("\nThis suggests TradingView uses:")
        print("  1. WebSocket for real-time data (wss://pushstream.tradingview.com)")
        print("  2. Obfuscated/minified API calls")
        print("  3. Data embedded in other bundles we haven't checked")


if __name__ == "__main__":
    main()
