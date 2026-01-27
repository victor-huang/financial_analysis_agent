#!/usr/bin/env python3
"""
Capture network requests from TradingView forecast page using browser automation.
This will show us the actual API endpoints used.

Requirements:
    pip install selenium webdriver-manager
    or
    pip install playwright && playwright install
"""

import sys
import json
import time


def capture_with_selenium(ticker="MU", exchange="NASDAQ"):
    """
    Use Selenium to capture network requests.
    """
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.common.exceptions import TimeoutException
    except ImportError:
        print(
            "Selenium not installed. Install with: pip install selenium webdriver-manager"
        )
        return None

    print("Using Selenium to capture network requests...")
    print("=" * 80)

    chrome_options = Options()
    chrome_options.add_argument("--headless")  # Run in background
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")

    # Enable logging of network requests
    chrome_options.set_capability("goog:loggingPrefs", {"performance": "ALL"})

    url = f"https://www.tradingview.com/symbols/{exchange}-{ticker}/forecast/"

    try:
        driver = webdriver.Chrome(options=chrome_options)
        driver.get(url)

        print(f"✓ Loaded page: {url}")
        print("Waiting for dynamic content to load...")

        # Wait for page to load
        time.sleep(10)

        # Get network logs
        logs = driver.get_log("performance")

        print(f"\n✓ Captured {len(logs)} network events")
        print("\nFiltering for API calls...")

        api_calls = []

        for log in logs:
            try:
                message = json.loads(log["message"])
                method = message.get("message", {}).get("method", "")

                # Look for network requests
                if method == "Network.responseReceived":
                    response = message["message"]["params"]["response"]
                    url_requested = response.get("url", "")

                    # Filter for relevant API calls
                    if any(
                        keyword in url_requested.lower()
                        for keyword in [
                            "financial",
                            "forecast",
                            "revenue",
                            "earning",
                            "estimate",
                            "api",
                            "data",
                            "symbol",
                            "quote",
                        ]
                    ):
                        if not any(
                            skip in url_requested
                            for skip in [".js", ".css", ".png", ".jpg", ".woff"]
                        ):
                            api_calls.append(
                                {
                                    "url": url_requested,
                                    "method": response.get("method", "GET"),
                                    "status": response.get("status", 0),
                                    "mimeType": response.get("mimeType", ""),
                                }
                            )

            except Exception as e:
                continue

        driver.quit()

        if api_calls:
            print(f"\n✓ Found {len(api_calls)} relevant API calls:")
            print("-" * 80)

            for i, call in enumerate(api_calls, 1):
                print(f"\n{i}. {call['method']} {call['url']}")
                print(f"   Status: {call['status']} | Type: {call['mimeType']}")

            return api_calls
        else:
            print("\n✗ No relevant API calls found")
            print("The data might be:")
            print("  - Loaded via WebSocket")
            print("  - Embedded in JavaScript bundles")
            print("  - Behind authentication")

        return None

    except Exception as e:
        print(f"✗ Error: {e}")
        try:
            driver.quit()
        except:
            pass
        return None


def manual_capture_instructions():
    """
    Provide instructions for manual API capture.
    """
    print("\n" + "=" * 80)
    print("MANUAL API CAPTURE INSTRUCTIONS")
    print("=" * 80)
    print(
        """
Since automated capture might not show all requests, please follow these steps:

1. Open Chrome/Firefox and navigate to:
   https://www.tradingview.com/symbols/NASDAQ-MU/forecast/

2. Open Developer Tools (F12 or Cmd+Option+I)

3. Go to the "Network" tab

4. Refresh the page (Cmd+R or Ctrl+R)

5. Look for XHR/Fetch requests that contain:
   - "financial"
   - "forecast"
   - "revenue"
   - "earnings"
   - "estimates"

6. Click on each interesting request and note:
   - Request URL
   - Request Method (GET/POST)
   - Request Headers
   - Request Payload (if POST)
   - Response data structure

7. Common patterns to look for:
   - https://scanner.tradingview.com/*
   - https://*.tradingview.com/api/*
   - https://*.tradingview.com/pine-facade/*
   - WebSocket connections (wss://)

8. Right-click on the request and select "Copy as cURL" or "Copy as fetch"
   and share that information.

WHAT TO LOOK FOR IN THE RESPONSE:
- Arrays of historical revenue data
- Arrays of historical EPS data
- Fiscal year/quarter identifiers
- Actual vs estimated values
"""
    )


def check_browser_extensions():
    """Check if user has required tools."""
    print("\nChecking available tools...")
    print("-" * 80)

    try:
        import selenium

        print("✓ Selenium installed")
        has_selenium = True
    except ImportError:
        print("✗ Selenium not installed (pip install selenium)")
        has_selenium = False

    try:
        import playwright

        print("✓ Playwright installed")
        has_playwright = True
    except ImportError:
        print("✗ Playwright not installed (pip install playwright)")
        has_playwright = False

    return has_selenium or has_playwright


def main():
    print("TradingView Network Request Capture")
    print("=" * 80)

    if check_browser_extensions():
        print("\nAttempting automated capture...")
        result = capture_with_selenium()

        if not result:
            manual_capture_instructions()
    else:
        print("\n✗ No browser automation tools available")
        manual_capture_instructions()


if __name__ == "__main__":
    main()
