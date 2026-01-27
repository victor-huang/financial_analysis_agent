#!/usr/bin/env python3
"""
TradingView scraper with Annual/Quarterly tab switching.
Extracts both annual (6+ years) and quarterly data.
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


class TradingViewAnnualScraper:
    """Scrape annual and quarterly financial data from TradingView."""

    def __init__(self, headless=True):
        """
        Initialize scraper.

        Args:
            headless: Run browser in headless mode
        """
        self.headless = headless
        self.driver = None

    def fetch_financial_data(
        self,
        ticker: str,
        exchange: str = "NASDAQ",
        include_annual: bool = True,
        include_quarterly: bool = True,
    ) -> Dict:
        """
        Fetch financial data for a ticker.

        Args:
            ticker: Stock ticker symbol
            exchange: Exchange name
            include_annual: Extract annual data
            include_quarterly: Extract quarterly data

        Returns:
            Dictionary with annual and quarterly data
        """
        print(f"\nFetching data for {exchange}:{ticker}...")
        print("=" * 80)

        try:
            self._setup_driver()

            # Load forecast page
            url = f"https://www.tradingview.com/symbols/{exchange}-{ticker}/forecast/"
            self.driver.get(url)
            print(f"✓ Loaded: {url}")

            print("Waiting for page to load...")
            time.sleep(8)

            result = {"ticker": ticker, "exchange": exchange}

            # Extract quarterly data first (default view)
            if include_quarterly:
                print("\n" + "-" * 80)
                print("Extracting QUARTERLY data...")
                print("-" * 80)
                quarterly_eps = self._extract_eps_data("quarterly")
                quarterly_revenue = self._extract_revenue_data("quarterly")
                result["quarterly"] = {
                    "eps": quarterly_eps,
                    "revenue": quarterly_revenue,
                }

            # Switch to annual and extract
            if include_annual:
                print("\n" + "-" * 80)
                print("Switching to ANNUAL view...")
                print("-" * 80)

                # Click the Annual button for EPS section
                if self._click_annual_button():
                    print("✓ Clicked Annual button")
                    time.sleep(5)  # Wait for chart to re-render

                    annual_eps = self._extract_eps_data("annual")
                    annual_revenue = self._extract_revenue_data("annual")
                    result["annual"] = {"eps": annual_eps, "revenue": annual_revenue}
                else:
                    print("✗ Could not find Annual button")

            return result

        except Exception as e:
            print(f"✗ Error: {e}")
            import traceback

            traceback.print_exc()
            return None
        finally:
            self._close_driver()

    def _setup_driver(self):
        """Set up Chrome driver."""
        chrome_options = Options()
        if self.headless:
            chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--window-size=1920,1080")

        self.driver = webdriver.Chrome(options=chrome_options)

    def _close_driver(self):
        """Close browser."""
        if self.driver:
            self.driver.quit()
            self.driver = None

    def _click_annual_button(self) -> bool:
        """
        Click the Annual button/tab to switch to annual view.

        Returns:
            True if button was found and clicked
        """
        try:
            # Look for buttons with text "Annual" or "FY"
            wait = WebDriverWait(self.driver, 10)

            # Try multiple selector strategies
            selectors = [
                "//button[contains(text(), 'Annual')]",
                "//button[@id='FY']",
                "//button[contains(@class, 'squareTabButton') and contains(., 'Annual')]",
                "//*[@role='tab' and contains(., 'Annual')]",
            ]

            for selector in selectors:
                try:
                    button = wait.until(
                        EC.element_to_be_clickable((By.XPATH, selector))
                    )
                    button.click()
                    return True
                except:
                    continue

            # If no button found, try to find by text
            buttons = self.driver.find_elements(By.TAG_NAME, "button")
            for button in buttons:
                if "Annual" in button.text or button.get_attribute("id") == "FY":
                    button.click()
                    return True

            return False

        except Exception as e:
            print(f"Error clicking annual button: {e}")
            return False

    def _extract_eps_data(self, period_type: str) -> Dict:
        """
        Extract EPS data from the current view.

        Args:
            period_type: "annual" or "quarterly"

        Returns:
            Dictionary with EPS data
        """
        html = self.driver.page_source
        soup = BeautifulSoup(html, "html.parser")

        # Extract period labels (years or quarters)
        periods = []
        for elem in soup.find_all("div", class_=re.compile(r"horizontalScaleValue")):
            period_text = elem.get_text(strip=True)

            # For annual: look for years like "2021", "2022"
            # For quarterly: look for quarters like "Q3 '24"
            if period_type == "annual":
                if re.match(r"^\d{4}$", period_text):  # Match 4-digit years
                    periods.append(period_text)
            else:
                if "'" in period_text:  # Match quarters like "Q3 '24"
                    periods.append(period_text)

        periods = list(dict.fromkeys(periods))  # Remove duplicates
        print(f"✓ Found {len(periods)} {period_type} periods: {periods}")

        # Extract y-axis scale
        scale_values = []
        for elem in soup.find_all("div", class_=re.compile(r"verticalScaleValue")):
            value_text = (
                elem.get_text(strip=True).replace("\u202a", "").replace("\u202c", "")
            )
            try:
                value = float(value_text)
                scale_values.append(value)
            except ValueError:
                continue

        scale_values = sorted(list(set(scale_values)))
        print(f"✓ Found scale values: {scale_values}")

        if not scale_values or not periods:
            return {}

        max_value = max(scale_values)
        min_value = min(scale_values)

        # Extract bar heights
        columns = soup.find_all("div", class_=re.compile(r"^column-[A-Za-z0-9]+$"))
        print(f"✓ Found {len(columns)} columns")

        data_points = []

        for i, column in enumerate(columns):
            if i >= len(periods):
                break

            bars = column.find_all("div", class_=re.compile(r"bar-"))

            reported_value = None
            estimate_value = None

            for bar in bars:
                style = bar.get("style", "")
                height_match = re.search(r"height:\s*max\(([0-9.]+)%", style)

                if not height_match:
                    continue

                height_percent = float(height_match.group(1))
                value = (height_percent / 100.0) * (max_value - min_value) + min_value

                # Blue = Reported, Gray = Estimate
                if "#3179F5" in style or "rgb(49, 121, 245)" in style:
                    reported_value = round(value, 2)
                elif "#EBEBEB" in style or "#A8A8A8" in style:
                    estimate_value = round(value, 2)

            data_points.append(
                {
                    "period": periods[i],
                    "reported": reported_value,
                    "estimate": estimate_value,
                }
            )

        # Separate historical and forecast
        historical = [d for d in data_points if d["reported"] is not None]
        forecast = [
            d
            for d in data_points
            if d["reported"] is None and d["estimate"] is not None
        ]

        print(
            f"✓ Extracted {len(historical)} historical and {len(forecast)} forecast periods"
        )

        return {
            "historical": historical,
            "forecast": forecast,
            "scale_range": [min_value, max_value],
        }

    def _extract_revenue_data(self, period_type: str) -> Dict:
        """
        Extract revenue data from the current view.
        Similar logic to EPS extraction.

        Args:
            period_type: "annual" or "quarterly"

        Returns:
            Dictionary with revenue data
        """
        # For now, using same extraction logic as EPS
        # In practice, you'd look for the Revenue section specifically
        # and extract from that chart

        html = self.driver.page_source

        # Look for "Revenue" heading and extract from that section
        if "revenue" in html.lower():
            print(f"✓ Found revenue data in {period_type} view")
            # TODO: Implement revenue-specific extraction
            return {
                "message": f"Revenue extraction for {period_type} - to be implemented"
            }

        return {}


def main():
    """Demo usage."""
    print("=" * 80)
    print("TradingView Annual + Quarterly Data Scraper")
    print("=" * 80)

    scraper = TradingViewAnnualScraper(headless=False)  # Set False to see browser

    # Fetch both annual and quarterly data
    data = scraper.fetch_financial_data(
        ticker="MU", exchange="NASDAQ", include_annual=True, include_quarterly=True
    )

    if data:
        print("\n" + "=" * 80)
        print("RESULTS")
        print("=" * 80)

        # Display Annual EPS
        if "annual" in data and data["annual"].get("eps", {}).get("historical"):
            print("\n" + "=" * 80)
            print("ANNUAL EPS (Historical)")
            print("=" * 80)
            print(f"{'Year':<10} {'Reported':>12} {'Estimate':>12}")
            print("-" * 35)

            for item in data["annual"]["eps"]["historical"]:
                year = item["period"]
                reported = f"${item['reported']:.2f}" if item["reported"] else "N/A"
                estimate = f"${item['estimate']:.2f}" if item["estimate"] else "N/A"
                print(f"{year:<10} {reported:>12} {estimate:>12}")

        # Display Quarterly EPS
        if "quarterly" in data and data["quarterly"].get("eps", {}).get("historical"):
            print("\n" + "=" * 80)
            print("QUARTERLY EPS (Recent History)")
            print("=" * 80)
            print(f"{'Quarter':<15} {'Reported':>12} {'Estimate':>12}")
            print("-" * 40)

            for item in data["quarterly"]["eps"]["historical"][
                :5
            ]:  # Show last 5 quarters
                quarter = item["period"]
                reported = f"${item['reported']:.2f}" if item["reported"] else "N/A"
                estimate = f"${item['estimate']:.2f}" if item["estimate"] else "N/A"
                print(f"{quarter:<15} {reported:>12} {estimate:>12}")

        # Save to file
        filename = f"tradingview_{data['ticker']}_annual_quarterly.json"
        with open(filename, "w") as f:
            json.dump(data, f, indent=2)
        print(f"\n✓ Saved complete data to: {filename}")

    else:
        print("\n✗ Failed to fetch data")


if __name__ == "__main__":
    main()
