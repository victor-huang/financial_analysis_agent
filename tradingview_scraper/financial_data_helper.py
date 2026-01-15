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


class FinancialDataFetcher:
    """Fetches detailed financial data for tickers."""
    
    def __init__(self, headless: bool = True):
        """
        Initialize the financial data fetcher.
        
        Args:
            headless: Run browser in headless mode
        """
        self.scraper = TradingViewFinalScraper(headless=headless)
    
    def get_financial_data(self, ticker: str, exchange: str = "NASDAQ") -> Optional[Dict]:
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
    
    def get_quarterly_revenue_history(self, ticker: str, exchange: str = "NASDAQ") -> list:
        """
        Get quarterly revenue history.
        
        Returns:
            List of quarterly revenue records (historical + forecast)
        """
        data = self.get_financial_data(ticker, exchange)
        if not data:
            return []
        
        return data.get("quarterly", {}).get("revenue", {}).get("historical", [])
    
    def get_yoy_data(self, ticker: str, exchange: str = "NASDAQ") -> Dict:
        """
        Get year-over-year comparison data.
        
        Returns:
            Dictionary with current quarter and same quarter last year
        """
        data = self.get_financial_data(ticker, exchange)
        if not data:
            return {}
        
        quarterly_eps = data.get("quarterly", {}).get("eps", {}).get("historical", [])
        quarterly_revenue = data.get("quarterly", {}).get("revenue", {}).get("historical", [])
        
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
        
        return result
    
    def close(self):
        """Close the scraper browser."""
        if hasattr(self.scraper, 'driver') and self.scraper.driver:
            self.scraper.driver.quit()
