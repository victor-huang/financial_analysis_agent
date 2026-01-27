#!/usr/bin/env python3
"""
Complete TradingView scraper - Annual & Quarterly EPS + Revenue.
Extracts 6+ years of annual data and recent quarterly data.
"""

import time
import re
import json
from typing import Dict, List, Optional
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup


class TradingViewCompleteScraper:
    """Complete scraper for TradingView financial data."""

    def __init__(self, headless=True):
        self.headless = headless
        self.driver = None

    def fetch_all_financial_data(self, ticker: str, exchange: str = "NASDAQ") -> Dict:
        """
        Fetch complete financial data: annual + quarterly EPS and Revenue.

        Args:
            ticker: Stock ticker
            exchange: Exchange name

        Returns:
            Complete financial data dictionary
        """
        print(f"\n{'='*80}")
        print(f"Fetching Complete Financial Data: {exchange}:{ticker}")
        print("=" * 80)

        try:
            self._setup_driver()

            url = f"https://www.tradingview.com/symbols/{exchange}-{ticker}/forecast/"
            self.driver.get(url)
            print(f"✓ Loaded: {url}")
            time.sleep(8)

            result = {
                "ticker": ticker,
                "exchange": exchange,
                "annual": {},
                "quarterly": {},
            }

            # Extract Quarterly EPS (default view)
            print(f"\n{'-'*80}")
            print("1. Extracting QUARTERLY EPS...")
            print("-" * 80)
            result["quarterly"]["eps"] = self._extract_chart_data("eps", "quarterly")

            # Click Annual button for EPS
            print(f"\n{'-'*80}")
            print("2. Switching to ANNUAL EPS...")
            print("-" * 80)
            if self._click_tab("Annual", section="eps"):
                time.sleep(5)
                result["annual"]["eps"] = self._extract_chart_data("eps", "annual")
            else:
                print("✗ Could not switch to annual EPS view")

            # Now handle Revenue section
            # Navigate to financials page or look for revenue on same page
            print(f"\n{'-'*80}")
            print("3. Checking for REVENUE data...")
            print("-" * 80)

            # Check if revenue section exists on forecast page
            html = self.driver.page_source
            if self._has_revenue_section(html):
                print("✓ Found revenue section on forecast page")

                # Click quarterly tab for revenue (if needed)
                if self._click_tab("Quarterly", section="revenue"):
                    time.sleep(5)
                    result["quarterly"]["revenue"] = self._extract_chart_data(
                        "revenue", "quarterly"
                    )

                # Click annual tab for revenue
                if self._click_tab("Annual", section="revenue"):
                    time.sleep(5)
                    result["annual"]["revenue"] = self._extract_chart_data(
                        "revenue", "annual"
                    )
            else:
                print("✗ Revenue data not found on forecast page")
                print("  (Revenue data may be on financials-overview page)")

            return result

        except Exception as e:
            print(f"✗ Error: {e}")
            import traceback

            traceback.print_exc()
            return None
        finally:
            self._close_driver()

    def _setup_driver(self):
        """Setup Chrome driver."""
        chrome_options = Options()
        if self.headless:
            chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--window-size=1920,1080")
        self.driver = webdriver.Chrome(options=chrome_options)

    def _close_driver(self):
        """Close browser."""
        if self.driver:
            self.driver.quit()

    def _has_revenue_section(self, html: str) -> bool:
        """Check if page has revenue chart section."""
        soup = BeautifulSoup(html, "html.parser")
        for heading in soup.find_all(["h1", "h2", "h3", "h4"]):
            if "revenue" in heading.get_text().lower():
                return True
        return False

    def _click_tab(self, tab_name: str, section: str = "eps") -> bool:
        """
        Click Annual or Quarterly tab.

        Args:
            tab_name: "Annual" or "Quarterly"
            section: "eps" or "revenue" (to find correct tab group)

        Returns:
            True if clicked successfully
        """
        try:
            # Find all buttons with the tab name
            buttons = self.driver.find_elements(
                By.XPATH, f"//button[contains(text(), '{tab_name}')]"
            )

            if not buttons:
                # Try by ID
                button_id = "FY" if tab_name == "Annual" else "FQ"
                buttons = self.driver.find_elements(By.ID, button_id)

            if buttons:
                # Click the first matching button
                # (In case of multiple sections, this might need refinement)
                buttons[0].click()
                print(f"✓ Clicked {tab_name} tab")
                return True

            return False

        except Exception as e:
            print(f"✗ Error clicking {tab_name} tab: {e}")
            return False

    def _extract_chart_data(self, data_type: str, period_type: str) -> Dict:
        """
        Extract chart data (EPS or Revenue).

        Args:
            data_type: "eps" or "revenue"
            period_type: "annual" or "quarterly"

        Returns:
            Extracted data dictionary
        """
        html = self.driver.page_source
        soup = BeautifulSoup(html, "html.parser")

        # Extract period labels
        periods = []
        for elem in soup.find_all("div", class_=re.compile(r"horizontalScaleValue")):
            text = elem.get_text(strip=True)

            if period_type == "annual":
                if re.match(r"^\d{4}$", text):  # Years
                    periods.append(text)
            else:
                if "'" in text:  # Quarters
                    periods.append(text)

        periods = list(dict.fromkeys(periods))
        print(f"  ✓ Found {len(periods)} {period_type} periods")

        # Extract scale
        scale_values = []
        for elem in soup.find_all("div", class_=re.compile(r"verticalScaleValue")):
            text = elem.get_text(strip=True).replace("\u202a", "").replace("\u202c", "")
            try:
                scale_values.append(float(text))
            except:
                pass

        scale_values = sorted(list(set(scale_values)))

        if not scale_values or not periods:
            return {}

        max_val = max(scale_values)
        min_val = min(scale_values)

        # Extract bars
        columns = soup.find_all("div", class_=re.compile(r"^column-[A-Za-z0-9]+$"))

        data_points = []
        for i, column in enumerate(columns):
            if i >= len(periods):
                break

            bars = column.find_all("div", class_=re.compile(r"bar-"))

            reported = None
            estimate = None

            for bar in bars:
                style = bar.get("style", "")
                match = re.search(r"height:\s*max\(([0-9.]+)%", style)

                if match:
                    height_pct = float(match.group(1))
                    value = (height_pct / 100.0) * (max_val - min_val) + min_val

                    if "#3179F5" in style:
                        reported = round(value, 2)
                    elif "#EBEBEB" in style or "#A8A8A8" in style:
                        estimate = round(value, 2)

            data_points.append(
                {"period": periods[i], "reported": reported, "estimate": estimate}
            )

        historical = [d for d in data_points if d["reported"] is not None]
        forecast = [
            d
            for d in data_points
            if d["reported"] is None and d["estimate"] is not None
        ]

        print(f"  ✓ Extracted {len(historical)} historical, {len(forecast)} forecast")

        return {
            "historical": historical,
            "forecast": forecast,
            "scale_range": [min_val, max_val],
        }


def main():
    """Demo."""
    scraper = TradingViewCompleteScraper(headless=False)

    data = scraper.fetch_all_financial_data("MU", "NASDAQ")

    if data:
        print(f"\n{'='*80}")
        print("SUMMARY")
        print("=" * 80)

        # Annual EPS
        if data["annual"].get("eps", {}).get("historical"):
            print("\n📊 ANNUAL EPS:")
            for item in data["annual"]["eps"]["historical"]:
                print(f"  {item['period']}: ${item['reported']}")

        # Quarterly EPS (recent)
        if data["quarterly"].get("eps", {}).get("historical"):
            print("\n📊 RECENT QUARTERLY EPS:")
            for item in data["quarterly"]["eps"]["historical"][-5:]:
                print(f"  {item['period']}: ${item['reported']}")

        # Save
        filename = f"tradingview_{data['ticker']}_complete.json"
        with open(filename, "w") as f:
            json.dump(data, f, indent=2)
        print(f"\n✓ Saved to: {filename}")


if __name__ == "__main__":
    main()
