#!/usr/bin/env python3
"""
TradingView Financial Data Scraper

Extracts EPS and Revenue data from TradingView forecast pages:
- Annual data: 5+ years of historical EPS & Revenue
- Quarterly data: 7+ quarters of historical EPS & Revenue
- Forward Estimates: 4 quarters ahead for both metrics

The scraper navigates the page, switches between Annual/Quarterly tabs,
and extracts data from DOM bar charts for both EPS and Revenue sections.
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
from selenium.webdriver.common.action_chains import ActionChains
from bs4 import BeautifulSoup


class TradingViewFinalScraper:
    """TradingView scraper for EPS and Revenue data extraction from forecast pages."""

    def __init__(self, headless=True):
        self.headless = headless
        self.driver = None

    def fetch_all_financial_data(self, ticker: str, exchange: str = "NASDAQ") -> Dict:
        """
        Fetch EPS and Revenue data from TradingView forecast page.

        Extracts:
        - Annual EPS & Revenue: 5+ years historical + forward estimates
        - Quarterly EPS & Revenue: 7+ quarters historical + forward estimates

        Args:
            ticker: Stock ticker symbol (e.g., "AAPL", "MU")
            exchange: Exchange name (default: "NASDAQ")

        Returns:
            Dictionary with structure:
            {
                "ticker": str,
                "exchange": str,
                "annual": {
                    "eps": {"historical": [...], "forecast": [...]},
                    "revenue": {"historical": [...], "forecast": [...]}
                },
                "quarterly": {
                    "eps": {"historical": [...], "forecast": [...]},
                    "revenue": {"historical": [...], "forecast": [...]}
                }
            }
        """
        print(f"\n{'='*80}")
        print(f"TradingView Financial Data Scraper")
        print(f"Ticker: {exchange}:{ticker}")
        print("=" * 80)

        try:
            self._setup_driver()

            url = f"https://www.tradingview.com/symbols/{exchange}-{ticker}/forecast/"
            self.driver.get(url)
            print(f"✓ Loaded: {url}")
            time.sleep(8)

            # Check if page exists (not 404 or error page)
            page_title = self.driver.title
            if "404" in page_title or "Not Found" in page_title:
                print(f"✗ Forecast page does not exist for {ticker}")
                print(f"  (Small-cap stocks often lack analyst coverage)")
                return None

            # Check for "No data" or similar messages
            page_source = self.driver.page_source
            if "no data available" in page_source.lower() or len(page_source) < 10000:
                print(f"✗ No forecast data available for {ticker}")
                return None

            result = {
                "ticker": ticker,
                "exchange": exchange,
                "annual": {},
                "quarterly": {},
            }

            # Extract EPS data (quarterly and annual)
            print(f"\n{'-'*80}")
            print("EXTRACTING EPS DATA")
            print("-" * 80)
            eps_data = self._extract_section_data("EPS")

            if eps_data:
                result["quarterly"]["eps"] = eps_data.get("quarterly", {})
                result["annual"]["eps"] = eps_data.get("annual", {})
                print("✓ EPS data extracted successfully")
            else:
                print("✗ Failed to extract EPS data")

            # Extract Revenue data (scroll to it first)
            print(f"\n{'-'*80}")
            print("EXTRACTING REVENUE DATA")
            print("-" * 80)
            revenue_data = self._extract_section_data("Revenue")

            if revenue_data:
                result["quarterly"]["revenue"] = revenue_data.get("quarterly", {})
                result["annual"]["revenue"] = revenue_data.get("annual", {})
                print("✓ Revenue data extracted successfully")
            else:
                print("✗ Failed to extract Revenue data")

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

    def _extract_section_data(self, section_name: str) -> Optional[Dict]:
        """
        Extract data from a specific section (EPS or Revenue).

        For Revenue, we need to use the table data since the chart DOM structure
        may show EPS values. The table is in the sibling div after the heading.

        Args:
            section_name: "EPS" or "Revenue"

        Returns:
            Dictionary with quarterly and annual data
        """
        # Find the section heading
        section_element = self._find_section(section_name)

        if not section_element:
            print(f"  ✗ Could not find {section_name} section")
            return None

        print(f"  ✓ Found {section_name} section")

        # Scroll to section
        self.driver.execute_script(
            "arguments[0].scrollIntoView(true);", section_element
        )
        time.sleep(2)

        result = {}

        # For Revenue, use table extraction; for EPS, use chart extraction
        if section_name == "Revenue":
            # Extract from table data instead of chart
            result = self._extract_revenue_from_table(section_element)
        else:
            # Extract quarterly data (default view)
            print(f"  → Extracting quarterly {section_name}...")
            result["quarterly"] = self._extract_chart_data_from_section(
                section_element, "quarterly"
            )

            # Click Annual button within this section
            if self._click_tab_in_section(section_element, "Annual"):
                time.sleep(5)
                print(f"  → Extracting annual {section_name}...")
                result["annual"] = self._extract_chart_data_from_section(
                    section_element, "annual"
                )
            else:
                print(f"  ✗ Could not switch to annual view for {section_name}")

        return result

    def _find_section(self, section_name: str) -> Optional[any]:
        """
        Find a section by its heading (EPS or Revenue).

        For Revenue, returns the H3 element itself since we need to navigate differently.
        For EPS, returns the container with chart and tabs.

        Returns:
            WebElement - either H3 (for Revenue) or container (for EPS)
        """
        try:
            # Look for H3 headings with exact text match
            headings = self.driver.find_elements(
                By.XPATH,
                f"//h3[@class='title-GQWAi9kx title-fptnPtZy' and text()='{section_name}']",
            )

            if not headings:
                # Fallback to contains search
                headings = self.driver.find_elements(
                    By.XPATH, f"//h3[contains(text(), '{section_name}')]"
                )

            if not headings:
                return None

            heading = headings[0]

            # For Revenue, return the H3 itself - we'll handle navigation in _extract_revenue_from_table
            if section_name == "Revenue":
                return heading

            # For EPS, find parent container with chart and tabs
            parent = heading
            for _ in range(10):  # Try up to 10 levels up
                parent = parent.find_element(By.XPATH, "..")
                class_name = parent.get_attribute("class") or ""

                # Check if this parent contains both the chart and tabs
                try:
                    tabs = parent.find_elements(By.XPATH, ".//button[@role='tab']")
                    charts = parent.find_elements(
                        By.XPATH, ".//*[contains(@class, 'chart')]"
                    )

                    if tabs and charts:
                        return parent
                except:
                    continue

            # Fallback: return the immediate parent of heading
            return heading.find_element(By.XPATH, "..")

        except Exception as e:
            print(f"  Error finding section: {e}")
            return None

    def _click_tab_in_section(self, section_element: any, tab_name: str) -> bool:
        """
        Click Annual or Quarterly tab within a specific section.

        Args:
            section_element: The section container element
            tab_name: "Annual" or "Quarterly"

        Returns:
            True if clicked successfully
        """
        try:
            # Find tabs within this section only
            tabs = section_element.find_elements(By.XPATH, ".//button[@role='tab']")

            for tab in tabs:
                if tab_name in tab.text or (
                    tab_name == "Annual" and tab.get_attribute("id") == "FY"
                ):
                    # Click using JavaScript to avoid interception
                    self.driver.execute_script("arguments[0].click();", tab)
                    print(f"    ✓ Clicked {tab_name} tab")
                    return True

            return False

        except Exception as e:
            print(f"    ✗ Error clicking {tab_name} tab: {e}")
            return False

    def _extract_first_chart_data(self) -> Optional[Dict]:
        """
        Extract data from the first chart found on the page (fallback method).

        Returns:
            Dictionary with quarterly and annual data
        """
        try:
            # Find first chart on page
            charts = self.driver.find_elements(
                By.XPATH, "//*[contains(@class, 'chart')]"
            )
            if not charts:
                return None

            # Try to extract quarterly first
            quarterly_data = self._extract_chart_data_from_html(
                self.driver.page_source, "quarterly"
            )

            # Click any Annual button we can find
            try:
                annual_button = self.driver.find_element(
                    By.XPATH, "//button[contains(text(), 'Annual') or @id='FY']"
                )
                self.driver.execute_script("arguments[0].click();", annual_button)
                time.sleep(5)
            except:
                pass

            annual_data = self._extract_chart_data_from_html(
                self.driver.page_source, "annual"
            )

            return {"quarterly": quarterly_data, "annual": annual_data}
        except Exception as e:
            print(f"  Error in fallback extraction: {e}")
            return None

    def _extract_chart_data_from_html(self, html: str, period_type: str) -> Dict:
        """Extract chart data from full page HTML."""
        soup = BeautifulSoup(html, "html.parser")

        # Extract periods
        periods = []
        for elem in soup.find_all("div", class_=re.compile(r"horizontalScaleValue")):
            text = elem.get_text(strip=True)
            if period_type == "annual" and re.match(r"^\d{4}$", text):
                periods.append(text)
            elif period_type == "quarterly" and "'" in text:
                periods.append(text)

        periods = list(dict.fromkeys(periods))[:20]  # Limit to first 20

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

        return {
            "historical": historical,
            "forecast": forecast,
            "scale_range": [min_val, max_val],
        }

    def _extract_revenue_from_table(self, section_element: any) -> Dict:
        """
        Extract revenue data from table structure.

        Revenue H3 is inside a parent container that holds both EPS and Revenue sections.
        Structure:
        - container-fptnPtZy (parent)
          - [0] heading for EPS
          - [1] chart for EPS
          - [2] table for EPS
          - [3] spacing
          - [4] heading for Revenue (contains our H3)
          - [5] chart for Revenue
          - [6] table for Revenue <- WE WANT THIS

        Args:
            section_element: The H3 element for Revenue

        Returns:
            Dictionary with quarterly and annual data
        """
        try:
            # section_element is the H3 element
            # Navigate: H3 -> heading div -> container-fptnPtZy (parent with both sections)
            heading_div = section_element.find_element(By.XPATH, "..")
            container = heading_div.find_element(By.XPATH, "..")

            # Get all children of the parent container
            children = container.find_elements(By.XPATH, "./*")

            print(f"    → Container has {len(children)} children")

            if len(children) < 7:
                print(f"    ✗ Expected 7 children, got {len(children)}")
                return {"quarterly": {}, "annual": {}}

            # Child [6] is the Revenue table container
            revenue_table_container = children[6]

            # Extract quarterly data (default view)
            print(f"  → Extracting quarterly Revenue from table...")
            quarterly_data = self._extract_table_data(
                revenue_table_container, "quarterly"
            )

            # Click Annual button to get annual data
            result = {"quarterly": quarterly_data}

            # Find Annual button in the Revenue heading (child [4])
            revenue_heading = children[4]
            tabs = revenue_heading.find_elements(By.XPATH, ".//button[@role='tab']")

            for tab in tabs:
                if "Annual" in tab.text or tab.get_attribute("id") == "FY":
                    self.driver.execute_script("arguments[0].click();", tab)
                    print(f"    ✓ Clicked Annual tab")
                    time.sleep(5)
                    break

            # Extract annual data from table
            print(f"  → Extracting annual Revenue from table...")
            annual_data = self._extract_table_data(revenue_table_container, "annual")
            result["annual"] = annual_data

            return result

        except Exception as e:
            print(f"    ✗ Error extracting revenue from table: {e}")
            import traceback

            traceback.print_exc()
            return {"quarterly": {}, "annual": {}}

    def _extract_table_data(self, table_container: any, period_type: str) -> Dict:
        """
        Extract data from table container.
        Uses x-position to align values with their corresponding year/quarter labels.

        Args:
            table_container: The container-Tv7LSjUz element
            period_type: "quarterly" or "annual"

        Returns:
            Dictionary with historical and forecast data
        """
        try:
            # Get all value cells with their positions
            values = table_container.find_elements(By.CLASS_NAME, "value-OxVAcLqi")

            if len(values) < 10:
                return {}

            # Separate period labels from data values based on content
            period_cells = []
            data_cells = []

            for v in values:
                text = v.text.replace("\u202a", "").replace("\u202c", "").strip()
                x_pos = v.location["x"]

                if period_type == "annual" and re.match(r"^\d{4}$", text):
                    period_cells.append({"text": text, "x": x_pos})
                elif period_type == "quarterly" and "'" in text:
                    period_cells.append({"text": text, "x": x_pos})
                elif text and text != "—":
                    # This is a data value (reported, estimate, or surprise)
                    parsed = self._parse_value(text)
                    if parsed is not None:
                        data_cells.append({"value": parsed, "x": x_pos, "raw": text})

            if not period_cells:
                return {}

            # Sort periods by x position
            period_cells.sort(key=lambda p: p["x"])

            # Find the x-range for periods that have data
            # Data cells should align with period columns
            min_data_x = min(d["x"] for d in data_cells) if data_cells else 0
            max_data_x = max(d["x"] for d in data_cells) if data_cells else 9999

            # Filter periods to only those that have corresponding data columns
            # A period has data if there's a data cell within ~50px of its x position
            periods_with_data = []
            for p in period_cells:
                has_data = any(abs(d["x"] - p["x"]) < 50 for d in data_cells)
                if has_data:
                    periods_with_data.append(p)

            if not periods_with_data:
                # Fallback: use all periods
                periods_with_data = period_cells

            # Now match data values to periods based on x-position proximity
            # Split data cells into reported (first row after labels) and estimates (second row)
            # by their approximate y-position or by order

            num_periods = len(periods_with_data)

            # Get reported and estimate values by index (they come in order after period labels)
            all_data_values = []
            for v in values:
                text = v.text.replace("\u202a", "").replace("\u202c", "").strip()
                if not re.match(r"^\d{4}$", text) and "'" not in text:
                    # Not a period label, so it's a data value
                    if "%" in text:
                        all_data_values.append(None)  # Surprise percentage
                    else:
                        all_data_values.append(self._parse_value(text))

            # First num_periods data values are "reported", next num_periods are "estimates"
            reported_values = (
                all_data_values[:num_periods]
                if len(all_data_values) >= num_periods
                else []
            )
            estimate_values = (
                all_data_values[num_periods : 2 * num_periods]
                if len(all_data_values) >= 2 * num_periods
                else []
            )

            # Build data points
            import datetime

            current_year = datetime.datetime.now().year
            data_points = []

            for idx, period_cell in enumerate(periods_with_data):
                period = period_cell["text"]
                reported = reported_values[idx] if idx < len(reported_values) else None
                estimate = estimate_values[idx] if idx < len(estimate_values) else None

                # For annual data, filter out future years that shouldn't have reported values
                if period_type == "annual" and period.isdigit():
                    year = int(period)
                    if year > current_year and reported is not None:
                        reported = None

                data_points.append(
                    {"period": period, "reported": reported, "estimate": estimate}
                )

            # Separate historical and forecast
            historical = [d for d in data_points if d["reported"] is not None]
            forecast = [
                d
                for d in data_points
                if d["reported"] is None and d["estimate"] is not None
            ]

            print(
                f"    ✓ Extracted {len(historical)} historical, {len(forecast)} forecast"
            )

            return {"historical": historical, "forecast": forecast}

        except Exception as e:
            print(f"    ✗ Error parsing table data: {e}")
            import traceback

            traceback.print_exc()
            return {}

    def _parse_value(self, text: str):
        """Parse a value string, handling B/M suffixes and dashes."""
        if text == "—" or text == "-" or not text:
            return None
        try:
            if "B" in text:
                return (
                    float(text.replace("B", "").strip()) * 1000
                )  # Convert to millions
            elif "M" in text:
                return float(text.replace("M", "").strip())
            else:
                return float(text)
        except:
            return None

    def _extract_chart_data_from_section(
        self, section_element: any, period_type: str
    ) -> Dict:
        """
        Extract chart data from a specific section.

        Args:
            section_element: The section container element
            period_type: "annual" or "quarterly"

        Returns:
            Extracted data dictionary
        """
        # Get HTML from the section
        section_html = section_element.get_attribute("outerHTML")
        soup = BeautifulSoup(section_html, "html.parser")

        # Extract period labels
        periods = []
        for elem in soup.find_all("div", class_=re.compile(r"horizontalScaleValue")):
            text = elem.get_text(strip=True)

            if period_type == "annual":
                if re.match(r"^\d{4}$", text):  # Years like "2021"
                    periods.append(text)
            else:
                if "'" in text:  # Quarters like "Q3 '24"
                    periods.append(text)

        periods = list(dict.fromkeys(periods))  # Remove duplicates

        # Extract scale values
        scale_values = []
        for elem in soup.find_all("div", class_=re.compile(r"verticalScaleValue")):
            text = elem.get_text(strip=True).replace("\u202a", "").replace("\u202c", "")
            try:
                scale_values.append(float(text))
            except:
                pass

        scale_values = sorted(list(set(scale_values)))

        if not scale_values or not periods:
            print(
                f"    ✗ No data found (periods: {len(periods)}, scale: {len(scale_values)})"
            )
            return {}

        max_val = max(scale_values)
        min_val = min(scale_values)

        print(f"    ✓ Found {len(periods)} periods, scale: {min_val}-{max_val}")

        # Extract bar data
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
                    # Scale might be different for revenue (billions) vs EPS (dollars)
                    value = (height_pct / 100.0) * (max_val - min_val) + min_val

                    # Blue = Reported, Gray = Estimate
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

        print(f"    ✓ Extracted {len(historical)} historical, {len(forecast)} forecast")

        return {
            "historical": historical,
            "forecast": forecast,
            "scale_range": [min_val, max_val],
        }


def main():
    """Demo."""
    scraper = TradingViewFinalScraper(headless=False)  # Set to False to see browser

    data = scraper.fetch_all_financial_data("MU", "NASDAQ")

    if data:
        print(f"\n{'='*80}")
        print("RESULTS SUMMARY")
        print("=" * 80)

        # Annual EPS
        if data.get("annual", {}).get("eps", {}).get("historical"):
            print("\n📊 ANNUAL EPS (Last 5 Years):")
            for item in data["annual"]["eps"]["historical"]:
                print(f"  {item['period']}: ${item['reported']}")

        # Annual Revenue
        if data.get("annual", {}).get("revenue", {}).get("historical"):
            print("\n💰 ANNUAL REVENUE (Last 5 Years):")
            for item in data["annual"]["revenue"]["historical"]:
                value = item["reported"]
                # Format revenue in billions if > 1000
                print(
                    f"  {item['period']}: ${value/1000:.2f}B"
                    if value > 1000
                    else f"  {item['period']}: ${value:.2f}"
                )

        # Recent Quarterly EPS
        if data.get("quarterly", {}).get("eps", {}).get("historical"):
            print("\n📈 RECENT QUARTERLY EPS:")
            for item in data["quarterly"]["eps"]["historical"][-5:]:
                print(f"  {item['period']}: ${item['reported']}")

        # Recent Quarterly Revenue
        if data.get("quarterly", {}).get("revenue", {}).get("historical"):
            print("\n💵 RECENT QUARTERLY REVENUE:")
            for item in data["quarterly"]["revenue"]["historical"][-5:]:
                value = item["reported"]
                print(
                    f"  {item['period']}: ${value/1000:.2f}B"
                    if value > 1000
                    else f"  {item['period']}: ${value:.2f}"
                )

        # Forward EPS Estimates
        if data.get("quarterly", {}).get("eps", {}).get("forecast"):
            print("\n🔮 FORWARD EPS ESTIMATES:")
            for item in data["quarterly"]["eps"]["forecast"][:4]:
                print(f"  {item['period']}: ${item['estimate']} (estimate)")

        # Forward Revenue Estimates
        if data.get("quarterly", {}).get("revenue", {}).get("forecast"):
            print("\n🔮 FORWARD REVENUE ESTIMATES:")
            for item in data["quarterly"]["revenue"]["forecast"][:4]:
                value = item["estimate"]
                print(
                    f"  {item['period']}: ${value/1000:.2f}B (estimate)"
                    if value > 1000
                    else f"  {item['period']}: ${value:.2f} (estimate)"
                )

        # Save
        filename = f"tradingview_{data['ticker']}_final.json"
        with open(filename, "w") as f:
            json.dump(data, f, indent=2)
        print(f"\n✓ Saved complete data to: {filename}")

    else:
        print("\n✗ Failed to fetch data")


if __name__ == "__main__":
    main()
