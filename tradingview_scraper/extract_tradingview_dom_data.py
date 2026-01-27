#!/usr/bin/env python3
"""
Extract financial data from TradingView forecast page by scraping the rendered DOM.
Uses Selenium to load the page and extract chart/table data.
"""

import time
import json
import re
from typing import Dict, List, Optional
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from bs4 import BeautifulSoup


class TradingViewDOMExtractor:
    """Extract financial data from TradingView DOM."""

    def __init__(self, headless=True):
        """
        Initialize the extractor.

        Args:
            headless: Run browser in headless mode (no visible window)
        """
        self.headless = headless
        self.driver = None

    def _setup_driver(self):
        """Set up Chrome driver with appropriate options."""
        chrome_options = Options()
        if self.headless:
            chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument(
            "--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )

        self.driver = webdriver.Chrome(options=chrome_options)

    def _close_driver(self):
        """Close the browser driver."""
        if self.driver:
            self.driver.quit()
            self.driver = None

    def extract_forecast_data(
        self, ticker: str, exchange: str = "NASDAQ"
    ) -> Optional[Dict]:
        """
        Extract financial data from TradingView forecast page.

        Args:
            ticker: Stock ticker symbol
            exchange: Exchange name

        Returns:
            Dictionary with extracted financial data
        """
        url = f"https://www.tradingview.com/symbols/{exchange}-{ticker}/forecast/"

        print(f"Loading: {url}")

        try:
            self._setup_driver()
            self.driver.get(url)

            print("Waiting for page to load...")
            time.sleep(8)  # Give time for JavaScript to load data

            # Get the page source after JavaScript execution
            html = self.driver.page_source

            # Save for debugging
            with open(
                f"tradingview_rendered_{ticker}.html", "w", encoding="utf-8"
            ) as f:
                f.write(html)
            print(f"✓ Saved rendered HTML to: tradingview_rendered_{ticker}.html")

            # Extract data using different strategies
            data = {
                "ticker": ticker,
                "exchange": exchange,
                "tables": self._extract_tables(html),
                "chart_data": self._extract_chart_data(),
                "text_data": self._extract_text_data(html),
            }

            return data

        except Exception as e:
            print(f"✗ Error: {e}")
            return None
        finally:
            self._close_driver()

    def _extract_tables(self, html: str) -> List[Dict]:
        """Extract data from HTML tables."""
        soup = BeautifulSoup(html, "html.parser")
        tables = soup.find_all("table")

        print(f"\n✓ Found {len(tables)} tables")

        table_data = []
        for i, table in enumerate(tables):
            rows = []
            for row in table.find_all("tr"):
                cells = [
                    cell.get_text(strip=True) for cell in row.find_all(["td", "th"])
                ]
                if cells:
                    rows.append(cells)

            if rows:
                table_data.append({"table_index": i, "rows": rows})

                # Print first few rows for inspection
                print(f"\nTable {i}:")
                for row in rows[:5]:
                    print(f"  {row}")

        return table_data

    def _extract_chart_data(self) -> Optional[Dict]:
        """
        Try to extract data from chart elements or data attributes.
        """
        if not self.driver:
            return None

        chart_data = {}

        try:
            # Look for common chart container elements
            selectors = [
                '[class*="chart"]',
                '[data-name*="chart"]',
                '[class*="forecast"]',
                "canvas",
                "svg",
            ]

            for selector in selectors:
                try:
                    elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    if elements:
                        print(
                            f"\n✓ Found {len(elements)} elements matching: {selector}"
                        )

                        for elem in elements[:3]:
                            # Get all data attributes
                            attrs = self.driver.execute_script(
                                "var items = {}; "
                                "for (index = 0; index < arguments[0].attributes.length; ++index) { "
                                "  items[arguments[0].attributes[index].name] = arguments[0].attributes[index].value "
                                "}; "
                                "return items;",
                                elem,
                            )

                            # Check for data attributes
                            data_attrs = {
                                k: v for k, v in attrs.items() if k.startswith("data-")
                            }
                            if data_attrs:
                                print(f"  Data attributes: {data_attrs}")
                                chart_data[selector] = data_attrs

                except:
                    continue

        except Exception as e:
            print(f"Error extracting chart data: {e}")

        return chart_data if chart_data else None

    def _extract_text_data(self, html: str) -> Dict:
        """Extract financial numbers from text content."""
        soup = BeautifulSoup(html, "html.parser")

        # Search for specific patterns in the text
        patterns = {
            "revenue": r"revenue[:\s]+\$?([\d,\.]+)\s*([BMK])?",
            "eps": r"EPS[:\s]+\$?([\d,\.]+)",
            "fiscal_year": r"(FY|fiscal year)\s*(\d{4})",
            "quarter": r"Q(\d)\s*(\d{4})",
        }

        extracted = {}
        text = soup.get_text()

        for key, pattern in patterns.items():
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                extracted[key] = matches[:10]  # Keep first 10 matches

        if extracted:
            print("\n✓ Extracted text patterns:")
            for key, matches in extracted.items():
                print(f"  {key}: {matches}")

        return extracted

    def extract_financials_page(
        self, ticker: str, exchange: str = "NASDAQ"
    ) -> Optional[Dict]:
        """
        Extract data from financials-overview page.

        Args:
            ticker: Stock ticker symbol
            exchange: Exchange name

        Returns:
            Dictionary with extracted financial data
        """
        url = f"https://www.tradingview.com/symbols/{exchange}-{ticker}/financials-overview/"

        print(f"\nLoading: {url}")

        try:
            self._setup_driver()
            self.driver.get(url)

            print("Waiting for page to load...")
            time.sleep(8)

            html = self.driver.page_source

            # Save for debugging
            with open(
                f"tradingview_financials_rendered_{ticker}.html", "w", encoding="utf-8"
            ) as f:
                f.write(html)
            print(
                f"✓ Saved rendered HTML to: tradingview_financials_rendered_{ticker}.html"
            )

            data = {
                "ticker": ticker,
                "exchange": exchange,
                "tables": self._extract_tables(html),
                "text_data": self._extract_text_data(html),
            }

            # Try to find specific financial sections
            sections = self._extract_financial_sections()
            if sections:
                data["sections"] = sections

            return data

        except Exception as e:
            print(f"✗ Error: {e}")
            return None
        finally:
            self._close_driver()

    def _extract_financial_sections(self) -> Optional[Dict]:
        """Extract specific financial data sections."""
        if not self.driver:
            return None

        sections = {}

        # Look for sections with financial keywords
        keywords = ["revenue", "earnings", "eps", "income", "balance"]

        for keyword in keywords:
            try:
                # Try different selector patterns
                selectors = [
                    f'//*[contains(text(), "{keyword}")]',
                    f'//div[contains(@class, "{keyword}")]',
                    f'//section[contains(@class, "{keyword}")]',
                ]

                for selector in selectors:
                    try:
                        elements = self.driver.find_elements(By.XPATH, selector)
                        if elements:
                            print(f"✓ Found {len(elements)} elements for: {keyword}")
                            sections[keyword] = [
                                elem.text for elem in elements[:5] if elem.text
                            ]
                            break
                    except:
                        continue

            except Exception as e:
                continue

        return sections if sections else None


def main():
    """Main execution."""
    print("=" * 80)
    print("TradingView DOM Data Extractor")
    print("=" * 80)

    ticker = "MU"
    exchange = "NASDAQ"

    extractor = TradingViewDOMExtractor(headless=False)  # Set to False to see browser

    # Extract forecast page
    print("\n" + "=" * 80)
    print("Extracting FORECAST page data")
    print("=" * 80)
    forecast_data = extractor.extract_forecast_data(ticker, exchange)

    if forecast_data:
        print("\n✓ Forecast data extracted!")
        print(json.dumps(forecast_data, indent=2, default=str)[:2000])

        # Save to file
        with open(f"tradingview_forecast_data_{ticker}.json", "w") as f:
            json.dump(forecast_data, f, indent=2, default=str)
        print(f"\n✓ Saved to: tradingview_forecast_data_{ticker}.json")

    # Extract financials page
    print("\n" + "=" * 80)
    print("Extracting FINANCIALS page data")
    print("=" * 80)
    financials_data = extractor.extract_financials_page(ticker, exchange)

    if financials_data:
        print("\n✓ Financials data extracted!")
        print(json.dumps(financials_data, indent=2, default=str)[:2000])

        # Save to file
        with open(f"tradingview_financials_data_{ticker}.json", "w") as f:
            json.dump(financials_data, f, indent=2, default=str)
        print(f"\n✓ Saved to: tradingview_financials_data_{ticker}.json")

    print("\n" + "=" * 80)
    print("Next Steps:")
    print("=" * 80)
    print("1. Check the saved JSON files for extracted data")
    print("2. Check the rendered HTML files to see the DOM structure")
    print("3. Look for patterns in tables/sections that contain the data we need")
    print("4. We can refine the extraction logic based on what we find")


if __name__ == "__main__":
    main()
