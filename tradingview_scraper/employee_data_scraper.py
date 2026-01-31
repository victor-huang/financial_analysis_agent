#!/usr/bin/env python3
"""
TradingView Employee Data Scraper

Extracts employee count and YoY change data from TradingView symbol pages.
Employee data is displayed in the statistics section with format:
- Current employees: 205
- Change (1Y): +55 (+36.67%)
"""

import time
import re
from typing import Dict, Optional
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


class EmployeeDataScraper:
    """Scraper for extracting employee data from TradingView symbol pages."""

    def __init__(self, headless: bool = True):
        self.headless = headless
        self.driver = None

    def _setup_driver(self, max_retries: int = 3):
        """Setup Chrome driver with retry logic.

        Args:
            max_retries: Maximum number of retry attempts (default: 3)
        """
        if self.driver:
            return

        chrome_options = Options()
        if self.headless:
            chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--window-size=1920,1080")

        last_error = None
        for attempt in range(1, max_retries + 1):
            try:
                self.driver = webdriver.Chrome(options=chrome_options)
                return
            except Exception as e:
                last_error = e
                if attempt < max_retries:
                    print(
                        f"  ⚠ Driver setup failed (attempt {attempt}/{max_retries}): {e}"
                    )
                    print(f"  → Retrying in 2 seconds...")
                    time.sleep(2)

        raise last_error

    def _close_driver(self):
        """Close browser."""
        if self.driver:
            self.driver.quit()
            self.driver = None

    def fetch_employee_data(
        self, ticker: str, exchange: str = "NASDAQ"
    ) -> Optional[Dict]:
        """
        Fetch employee count and change data for a ticker.

        Args:
            ticker: Stock ticker symbol
            exchange: Exchange name (NASDAQ, NYSE, etc.)

        Returns:
            Dictionary with employee data:
            {
                "employee_count": int,
                "employee_change_1y": int,
                "employee_change_1y_percent": float
            }
            Returns None if data not found.
        """
        try:
            self._setup_driver()

            url = f"https://www.tradingview.com/symbols/{exchange}-{ticker}/"
            self.driver.get(url)
            print(f"  → Loading {url}")

            time.sleep(5)

            page_source = self.driver.page_source

            result = self._parse_employee_data(page_source)

            if result:
                print(
                    f"  ✓ Found employee data: {result['employee_count']} employees, "
                    f"Change: {result['employee_change_1y_percent']}%"
                )
            else:
                print(f"  ⚠ No employee data found for {ticker}")

            return result

        except Exception as e:
            print(f"  ✗ Error fetching employee data: {e}")
            return None

    def fetch_employee_data_reuse_driver(
        self, ticker: str, exchange: str = "NASDAQ", driver: webdriver.Chrome = None
    ) -> Optional[Dict]:
        """
        Fetch employee data using an existing WebDriver instance.
        This is more efficient when processing multiple tickers.

        Args:
            ticker: Stock ticker symbol
            exchange: Exchange name
            driver: Existing WebDriver instance

        Returns:
            Dictionary with employee data or None
        """
        if not driver:
            return self.fetch_employee_data(ticker, exchange)

        try:
            url = f"https://www.tradingview.com/symbols/{exchange}-{ticker}/"
            driver.get(url)

            time.sleep(5)

            page_source = driver.page_source
            return self._parse_employee_data(page_source)

        except Exception as e:
            print(f"  ✗ Error fetching employee data: {e}")
            return None

    def _parse_employee_data(self, html: str) -> Optional[Dict]:
        """
        Parse employee data from page HTML.

        Looks for patterns like:
        - "205 employees" or "166 K employees"
        - "Change (1Y) +55 +36.67%" or "Change (1Y) -10 -5.00%"

        Args:
            html: Page HTML source

        Returns:
            Dictionary with parsed employee data or None
        """
        result = {
            "employee_count": None,
            "employee_change_1y": None,
            "employee_change_1y_percent": None,
        }

        # Strip Unicode directional formatting characters that TradingView uses
        # U+202A (LEFT-TO-RIGHT EMBEDDING), U+202C (POP DIRECTIONAL FORMATTING)
        # U+200E (LEFT-TO-RIGHT MARK), U+200F (RIGHT-TO-LEFT MARK)
        # U+202F (NARROW NO-BREAK SPACE), U+FEFF (BOM/ZWNBSP)
        clean_html = html.replace("\u202a", "").replace("\u202c", "")
        clean_html = clean_html.replace("\u200e", "").replace("\u200f", "")
        clean_html = clean_html.replace("\u202f", " ").replace("\ufeff", "")

        # Pattern 1: Employee count with K suffix (e.g., "166 K employees" or "217K employees")
        count_match_k = re.search(
            r"(\d+(?:\.\d+)?)\s*K\s*(?:employees|Employees)", clean_html, re.IGNORECASE
        )
        if count_match_k:
            result["employee_count"] = int(float(count_match_k.group(1)) * 1000)

        # Pattern 2: Employee count without K (e.g., "205 employees")
        if not result["employee_count"]:
            count_match = re.search(
                r"(\d{1,3}(?:,\d{3})*|\d+)\s*(?:employees|Employees)",
                clean_html,
                re.IGNORECASE,
            )
            if count_match:
                count_str = count_match.group(1).replace(",", "")
                result["employee_count"] = int(count_str)

        # Pattern 3: Look for employee change in the employees-section
        # Format in HTML: "Change (1Y)" label followed by value like "−11.8 K −5.44%" or "+55 +36.67%"
        # The value may have K suffix for thousands and uses Unicode minus (−)
        change_pattern = re.search(
            r"([+\-−]?\d+(?:\.\d+)?)\s*K?\s*([+\-−]\d+(?:\.\d+)?)\s*%", clean_html
        )

        # Look more specifically in the employees section for change data
        employees_section = re.search(
            r"employees-section.*?Change\s*\(1Y\).*?([+\-−]?\d+(?:\.\d+)?)\s*K?\s*([+\-−]\d+(?:\.\d+)?)\s*%",
            clean_html,
            re.DOTALL | re.IGNORECASE,
        )

        if employees_section:
            change_abs_str = employees_section.group(1).replace("−", "-")
            change_pct_str = employees_section.group(2).replace("−", "-")

            try:
                # Convert K suffix to actual number if present
                abs_value = float(change_abs_str)
                # Check if there's a K after the number in the match
                if "K" in employees_section.group(0).split(change_pct_str)[0]:
                    abs_value = abs_value * 1000
                result["employee_change_1y"] = int(abs_value)
            except ValueError:
                pass

            try:
                result["employee_change_1y_percent"] = float(change_pct_str)
            except ValueError:
                pass

        # Only return if we found at least employee count
        if result["employee_count"] is not None:
            return result

        return None

    def close(self):
        """Close the scraper browser."""
        self._close_driver()


def main():
    """Demo usage."""
    print("=" * 80)
    print("TradingView Employee Data Scraper")
    print("=" * 80)

    scraper = EmployeeDataScraper(headless=True)

    test_tickers = [
        ("WFC", "NYSE"),
        ("APLD", "NASDAQ"),
        ("AAPL", "NASDAQ"),
    ]

    for ticker, exchange in test_tickers:
        print(f"\n{'='*60}")
        print(f"Testing: {exchange}:{ticker}")
        print("=" * 60)

        data = scraper.fetch_employee_data(ticker, exchange)

        if data:
            print(f"\nResults for {ticker}:")
            print(f"  Employee Count: {data['employee_count']:,}")
            if data["employee_change_1y"] is not None:
                print(f"  Change (1Y): {data['employee_change_1y']:+,}")
            if data["employee_change_1y_percent"] is not None:
                print(f"  Change %: {data['employee_change_1y_percent']:+.2f}%")
        else:
            print(f"\n✗ No employee data found for {ticker}")

    scraper.close()


if __name__ == "__main__":
    main()
