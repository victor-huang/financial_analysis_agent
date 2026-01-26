#!/usr/bin/env python3
"""
Helper functions for fetching detailed financial data using the scraper.
"""

import sys
import os
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
        Get year-over-year comparison data including employee headcount change.

        Returns:
            Dictionary with current quarter and same quarter last year,
            plus employee change data.
        """
        data = self.get_financial_data(ticker, exchange)
        if not data:
            return {}

        quarterly_eps = data.get("quarterly", {}).get("eps", {}).get("historical", [])
        quarterly_revenue = (
            data.get("quarterly", {}).get("revenue", {}).get("historical", [])
        )

        result = {}

        # Get most recent quarter (current)
        if quarterly_eps:
            result["eps_current_q"] = quarterly_eps[-1].get("reported")
            result["eps_current_period"] = quarterly_eps[-1].get("period")

            # Get same quarter last year (4 quarters back)
            if len(quarterly_eps) >= 5:
                result["eps_last_year_q"] = quarterly_eps[-5].get("reported")
                result["eps_last_year_period"] = quarterly_eps[-5].get("period")

            # Get previous quarter (1 quarter back)
            if len(quarterly_eps) >= 2:
                result["eps_last_q"] = quarterly_eps[-2].get("reported")

        if quarterly_revenue:
            result["revenue_current_q"] = quarterly_revenue[-1].get("reported")
            result["revenue_current_period"] = quarterly_revenue[-1].get("period")

            # Get same quarter last year (4 quarters back)
            if len(quarterly_revenue) >= 5:
                result["revenue_last_year_q"] = quarterly_revenue[-5].get("reported")
                result["revenue_last_year_period"] = quarterly_revenue[-5].get("period")

            # Get previous quarter (1 quarter back)
            if len(quarterly_revenue) >= 2:
                result["revenue_last_q"] = quarterly_revenue[-2].get("reported")

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
