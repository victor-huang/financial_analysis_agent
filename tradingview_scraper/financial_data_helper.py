#!/usr/bin/env python3
"""
Helper functions for fetching detailed financial data using the scraper.
"""

import sys
import os
import re
import datetime
from typing import Dict, Optional

# Add current directory to path to import the scraper
sys.path.insert(0, os.path.dirname(__file__))

from tradingview_final_scraper import TradingViewFinalScraper
from employee_data_scraper import EmployeeDataScraper


class FinancialDataFetcher:
    """Fetches detailed financial data for tickers."""

    def __init__(self, headless: bool = True):
        """
        Initialize the financial data fetcher.

        Args:
            headless: Run browser in headless mode
        """
        self.scraper = TradingViewFinalScraper(headless=headless)
        self.employee_scraper = EmployeeDataScraper(headless=headless)

    def get_financial_data(
        self, ticker: str, exchange: str = "NASDAQ"
    ) -> Optional[Dict]:
        """
        Fetch complete financial data for a ticker.

        Args:
            ticker: Stock ticker symbol
            exchange: Exchange name (NASDAQ, NYSE, etc.)

        Returns:
            Dictionary with financial data or None if failed
        """
        try:
            print(f"  Scraping detailed data for {ticker}...")
            data = self.scraper.fetch_all_financial_data(ticker, exchange)
            return data
        except Exception as e:
            print(f"  ✗ Error fetching data for {ticker}: {e}")
            return None

    def get_quarterly_eps_history(self, ticker: str, exchange: str = "NASDAQ") -> list:
        """
        Get quarterly EPS history.

        Returns:
            List of quarterly EPS records (historical + forecast)
        """
        data = self.get_financial_data(ticker, exchange)
        if not data:
            return []

        return data.get("quarterly", {}).get("eps", {}).get("historical", [])

    def get_quarterly_revenue_history(
        self, ticker: str, exchange: str = "NASDAQ"
    ) -> list:
        """
        Get quarterly revenue history.

        Returns:
            List of quarterly revenue records (historical + forecast)
        """
        data = self.get_financial_data(ticker, exchange)
        if not data:
            return []

        return data.get("quarterly", {}).get("revenue", {}).get("historical", [])

    def get_employee_data(
        self, ticker: str, exchange: str = "NASDAQ"
    ) -> Optional[Dict]:
        """
        Fetch employee count and YoY change data.

        Args:
            ticker: Stock ticker symbol
            exchange: Exchange name

        Returns:
            Dictionary with employee data:
            {
                "employee_count": int,
                "employee_change_1y": int,
                "employee_change_1y_percent": float
            }
        """
        try:
            print(f"  Fetching employee data for {ticker}...")
            return self.employee_scraper.fetch_employee_data(ticker, exchange)
        except Exception as e:
            print(f"  ✗ Error fetching employee data for {ticker}: {e}")
            return None

    def get_yoy_data(self, ticker: str, exchange: str = "NASDAQ") -> Dict:
        """
        Get comprehensive financial data including historical, YoY, and forecast data.

        Returns:
            Dictionary with quarterly/annual historical data and forecasts.
        """
        data = self.get_financial_data(ticker, exchange)
        if not data:
            return {}

        # Extract all data sections
        quarterly_eps_hist = (
            data.get("quarterly", {}).get("eps", {}).get("historical", [])
        )
        quarterly_eps_fc = data.get("quarterly", {}).get("eps", {}).get("forecast", [])
        quarterly_rev_hist = (
            data.get("quarterly", {}).get("revenue", {}).get("historical", [])
        )
        quarterly_rev_fc = (
            data.get("quarterly", {}).get("revenue", {}).get("forecast", [])
        )
        annual_eps_hist = data.get("annual", {}).get("eps", {}).get("historical", [])
        annual_eps_fc = data.get("annual", {}).get("eps", {}).get("forecast", [])
        annual_rev_hist = (
            data.get("annual", {}).get("revenue", {}).get("historical", [])
        )
        annual_rev_fc = data.get("annual", {}).get("revenue", {}).get("forecast", [])

        result = {}

        # --- Quarterly EPS ---
        if quarterly_eps_hist:
            # Most recent quarter reported
            result["eps_q_reported"] = quarterly_eps_hist[-1].get("reported")
            result["eps_q_estimate"] = quarterly_eps_hist[-1].get("estimate")
            # Same quarter last year (4 quarters back)
            if len(quarterly_eps_hist) >= 5:
                result["eps_same_q_last_y"] = quarterly_eps_hist[-5].get("reported")

        # Next quarter EPS forecast
        if quarterly_eps_fc:
            result["eps_next_q_fc"] = quarterly_eps_fc[0].get("estimate")
            # If multiple forecasts, second one could be analyst revision
            if len(quarterly_eps_fc) >= 2:
                result["eps_next_q_analys"] = quarterly_eps_fc[0].get("estimate")

        # --- Quarterly Revenue ---
        if quarterly_rev_hist:
            # Most recent quarter reported
            result["rev_q_reported"] = quarterly_rev_hist[-1].get("reported")
            result["rev_q_estimate"] = quarterly_rev_hist[-1].get("estimate")
            # Same quarter last year (4 quarters back)
            if len(quarterly_rev_hist) >= 5:
                result["rev_same_q_last_y"] = quarterly_rev_hist[-5].get("reported")
            # Previous quarter (last Q)
            if len(quarterly_rev_hist) >= 2:
                result["rev_last_q"] = quarterly_rev_hist[-2].get("reported")
            # Last Q same quarter last year (5 quarters back from last Q = 6 from current)
            if len(quarterly_rev_hist) >= 6:
                result["rev_last_q_last_y"] = quarterly_rev_hist[-6].get("reported")

        # Next quarter Revenue forecast
        if quarterly_rev_fc:
            result["rev_next_q_fc"] = quarterly_rev_fc[0].get("estimate")
            if len(quarterly_rev_fc) >= 1:
                result["rev_next_q_analys"] = quarterly_rev_fc[0].get("estimate")

        # --- Determine current reporting year from quarterly data ---
        current_reporting_year = None
        if quarterly_eps_hist:
            last_quarter_period = quarterly_eps_hist[-1].get("period", "")
            # Parse period like "Q4 '25" to get year 2025
            match = re.search(r"'(\d{2})$", last_quarter_period)
            if match:
                year_suffix = int(match.group(1))
                current_reporting_year = (
                    2000 + year_suffix if year_suffix < 50 else 1900 + year_suffix
                )

        # --- Annual Revenue ---
        # Combine historical and forecast, filter invalid years
        all_annual_rev = annual_rev_hist + annual_rev_fc
        current_calendar_year = datetime.datetime.now().year
        valid_annual_rev = [
            item
            for item in all_annual_rev
            if item.get("period", "").isdigit()
            and int(item["period"]) <= current_calendar_year
        ]
        # Sort by year
        valid_annual_rev.sort(key=lambda x: int(x["period"]))
        # Build a dict for easy lookup by year
        annual_rev_by_year = {item["period"]: item for item in valid_annual_rev}

        # Determine anchor year for annual data:
        # 1. Use current_reporting_year from quarterly data if available in annual data
        # 2. Fall back to most recent year with reported revenue
        anchor_year = None

        # First, try current_reporting_year (from quarterly data)
        if current_reporting_year and str(current_reporting_year) in annual_rev_by_year:
            anchor_year = current_reporting_year
        else:
            # Fall back to most recent year with actual reported revenue
            for item in reversed(valid_annual_rev):
                if item.get("reported") is not None:
                    anchor_year = int(item["period"])
                    break

        if anchor_year:
            # rev_full_y_est: estimate for the anchor year (current reporting year)
            result["rev_full_y_est"] = annual_rev_by_year.get(str(anchor_year), {}).get(
                "estimate"
            )
            result["rev_full_y_last_y"] = annual_rev_by_year.get(
                str(anchor_year - 1), {}
            ).get("reported")
            result["rev_y_2y_ago"] = annual_rev_by_year.get(str(anchor_year - 2), {}).get(
                "reported"
            )

        # --- Annual EPS ---
        # Combine historical and forecast, filter invalid years
        all_annual_eps = annual_eps_hist + annual_eps_fc
        valid_annual_eps = [
            item
            for item in all_annual_eps
            if item.get("period", "").isdigit()
            and int(item["period"]) <= current_calendar_year
        ]
        valid_annual_eps.sort(key=lambda x: int(x["period"]))
        annual_eps_by_year = {item["period"]: item for item in valid_annual_eps}

        # Determine anchor year for annual EPS:
        # 1. Use current_reporting_year from quarterly data if available
        # 2. Fall back to most recent year with reported EPS
        eps_anchor_year = None

        if current_reporting_year and str(current_reporting_year) in annual_eps_by_year:
            eps_anchor_year = current_reporting_year
        else:
            for item in reversed(valid_annual_eps):
                if item.get("reported") is not None:
                    eps_anchor_year = int(item["period"])
                    break

        if eps_anchor_year:
            result["eps_full_y_est"] = annual_eps_by_year.get(str(eps_anchor_year), {}).get(
                "estimate"
            )
            result["eps_full_y_last_y"] = annual_eps_by_year.get(
                str(eps_anchor_year - 1), {}
            ).get("reported")
            result["eps_y_2y_ago"] = annual_eps_by_year.get(str(eps_anchor_year - 2), {}).get(
                "reported"
            )

        # Fetch employee data
        employee_data = self.get_employee_data(ticker, exchange)
        if employee_data:
            result["employee_count"] = employee_data.get("employee_count")
            result["employee_change_1y"] = employee_data.get("employee_change_1y")
            result["employee_change_1y_percent"] = employee_data.get(
                "employee_change_1y_percent"
            )

        return result

    def close(self):
        """Close all scraper browsers."""
        if hasattr(self.scraper, "driver") and self.scraper.driver:
            self.scraper.driver.quit()
        if hasattr(self.employee_scraper, "driver") and self.employee_scraper.driver:
            self.employee_scraper.close()
