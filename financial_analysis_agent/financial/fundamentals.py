"""Fundamental analysis module for evaluating company financials."""
import logging
from typing import Dict, List, Optional, Tuple, Union
import pandas as pd
import numpy as np
from datetime import datetime

logger = logging.getLogger(__name__)

class CompanyFundamentals:
    """Class for analyzing company fundamentals."""
    
    def __init__(self, ticker: str, data_fetcher=None):
        """Initialize with a ticker symbol and optional data fetcher."""
        self.ticker = ticker.upper()
        self.data_fetcher = data_fetcher
        self._income_statement = None
        self._balance_sheet = None
        self._cash_flow = None
        self._info = None
    
    def load_financials(self, period: str = 'annual') -> bool:
        """Load financial statements.
        period: 'annual' or 'quarterly'
        """
        try:
            if not self.data_fetcher:
                from .data_fetcher import FinancialDataFetcher
                self.data_fetcher = FinancialDataFetcher()
            
            self._income_statement = self.data_fetcher.get_financials(
                self.ticker, 'income', period)
            self._balance_sheet = self.data_fetcher.get_financials(
                self.ticker, 'balance', period)
            self._cash_flow = self.data_fetcher.get_financials(
                self.ticker, 'cashflow', period)
            
            return all([self._income_statement is not None, 
                       self._balance_sheet is not None, 
                       self._cash_flow is not None])
        except Exception as e:
            logger.error(f"Error loading financials for {self.ticker}: {str(e)}")
            return False
    
    def get_financial_ratios(self, period: str = 'annual') -> Dict[str, float]:
        """Calculate key financial ratios for the latest period.
        period: 'annual' or 'quarterly'
        """
        if not all([self._income_statement is not None, 
                   self._balance_sheet is not None, 
                   self._cash_flow is not None]):
            if not self.load_financials(period=period):
                return {}
        
        try:
            # Get the most recent period's data
            income = self._income_statement.iloc[0]
            balance = self._balance_sheet.iloc[0]
            cash_flow = self._cash_flow.iloc[0]
            
            # Extract common line items with error handling
            total_revenue = income.get('Total Revenue', 0) or income.get('Revenue', 0) or 0
            gross_profit = income.get('Gross Profit', 0) or 0
            operating_income = income.get('Operating Income', 0) or income.get('Operating Income or Loss', 0) or 0
            net_income = income.get('Net Income', 0) or income.get('Net Income From Continuing Ops', 0) or 0
            total_assets = balance.get('Total Assets', 1) or 1  # Avoid division by zero
            total_liabilities = balance.get('Total Liabilities', 0) or 0
            total_equity = balance.get('Total Equity', 0) or balance.get("Total Stockholder Equity", 0) or 0
            current_assets = balance.get('Total Current Assets', 0) or 0
            current_liabilities = balance.get('Total Current Liabilities', 0) or 0
            inventory = balance.get('Inventory', 0) or 0
            operating_cash_flow = cash_flow.get('Total Cash From Operating Activities', 0) or 0
            capex = abs(cash_flow.get('Capital Expenditures', 0) or 0)
            
            # Calculate ratios
            ratios = {
                # Profitability Ratios
                'gross_margin': self._safe_divide(gross_profit, total_revenue) * 100,
                'operating_margin': self._safe_divide(operating_income, total_revenue) * 100,
                'net_margin': self._safe_divide(net_income, total_revenue) * 100,
                'return_on_assets': self._safe_divide(net_income, total_assets) * 100,
                'return_on_equity': self._safe_divide(net_income, total_equity) * 100,
                
                # Liquidity Ratios
                'current_ratio': self._safe_divide(current_assets, current_liabilities),
                'quick_ratio': self._safe_divide(current_assets - inventory, current_liabilities),
                
                # Leverage Ratios
                'debt_to_equity': self._safe_divide(total_liabilities, total_equity),
                'debt_to_assets': self._safe_divide(total_liabilities, total_assets),
                
                # Efficiency Ratios
                'asset_turnover': self._safe_divide(total_revenue, total_assets),
                
                # Cash Flow Ratios
                'operating_cash_flow_ratio': self._safe_divide(operating_cash_flow, total_liabilities),
                'free_cash_flow': operating_cash_flow - capex,
                'free_cash_flow_margin': self._safe_divide(operating_cash_flow - capex, total_revenue) * 100,
                
                # Valuation Ratios (require market data)
                'price_to_earnings': None,  # Will be filled by market data
                'price_to_book': None,      # Will be filled by market data
                'ev_to_ebitda': None        # Will be filled by market data
            }
            
            return ratios
            
        except Exception as e:
            logger.error(f"Error calculating financial ratios for {self.ticker}: {str(e)}")
            return {}
    
    def get_historical_ratios(self, years: int = 5) -> Dict[str, List[float]]:
        """Backward-compatible annual historical ratios over N years."""
        return self.get_periodic_ratios(period='annual', count=years)

    def get_periodic_ratios(self, period: str = 'annual', count: int = 8) -> Dict[str, List[float]]:
        """Get financial ratios for multiple periods.
        - period: 'annual' or 'quarterly'
        - count: number of periods to include (e.g., 5 years or 8 quarters)
        Returns dict of lists including period labels and ratio series.
        """
        if not all([self._income_statement is not None, 
                   self._balance_sheet is not None, 
                   self._cash_flow is not None]):
            if not self.load_financials(period=period):
                return {}
        
        try:
            # Determine number of periods
            num = min(count, len(self._income_statement))
            
            ratios = {
                'period_end': [],
                'label': [],
                'revenue': [],
                'gross_margin': [],
                'operating_margin': [],
                'net_margin': [],
                'return_on_equity': [],
                'debt_to_equity': [],
                'current_ratio': []
            }
            
            for i in range(num):
                # Get data for this period (most recent first)
                income = self._income_statement.iloc[i]
                balance = self._balance_sheet.iloc[i]
                
                # Extract line items
                total_revenue = income.get('Total Revenue', 0) or income.get('Revenue', 0) or 0
                gross_profit = income.get('Gross Profit', 0) or 0
                operating_income = income.get('Operating Income', 0) or income.get('Operating Income or Loss', 0) or 0
                net_income = income.get('Net Income', 0) or income.get('Net Income From Continuing Ops', 0) or 0
                total_equity = balance.get('Total Equity', 0) or balance.get("Total Stockholder Equity", 0) or 1
                total_liabilities = balance.get('Total Liabilities', 0) or 0
                current_assets = balance.get('Total Current Assets', 0) or 0
                current_liabilities = balance.get('Total Current Liabilities', 0) or 1
                
                # Calculate and store ratios
                idx = self._income_statement.index[i]
                # idx is a pandas Timestamp per yfinance. Build label by period type
                period_end = getattr(idx, 'to_pydatetime', lambda: idx)()
                ratios['period_end'].append(period_end.strftime('%Y-%m-%d'))
                if period == 'quarterly':
                    q = (period_end.month - 1) // 3 + 1
                    ratios['label'].append(f"{period_end.year}Q{q}")
                else:
                    ratios['label'].append(str(period_end.year))
                ratios['revenue'].append(total_revenue / 1e9)  # In billions
                ratios['gross_margin'].append(self._safe_divide(gross_profit, total_revenue) * 100)
                ratios['operating_margin'].append(self._safe_divide(operating_income, total_revenue) * 100)
                ratios['net_margin'].append(self._safe_divide(net_income, total_revenue) * 100)
                ratios['return_on_equity'].append(self._safe_divide(net_income, total_equity) * 100)
                ratios['debt_to_equity'].append(self._safe_divide(total_liabilities, total_equity))
                ratios['current_ratio'].append(self._safe_divide(current_assets, current_liabilities))
            
            return ratios
            
        except Exception as e:
            logger.error(f"Error calculating historical ratios for {self.ticker}: {str(e)}")
            return {}
    
    def analyze_financial_health(self) -> Dict[str, Union[str, float]]:
        """Analyze the company's financial health and return a summary."""
        ratios = self.get_financial_ratios()
        
        if not ratios:
            return {"error": "Could not calculate financial ratios"}
        
        # Initialize analysis dictionary
        analysis = {
            "profitability": {
                "score": 0,
                "metrics": {}
            },
            "liquidity": {
                "score": 0,
                "metrics": {}
            },
            "leverage": {
                "score": 0,
                "metrics": {}
            },
            "efficiency": {
                "score": 0,
                "metrics": {}
            },
            "overall_score": 0
        }
        
        # Analyze profitability
        if ratios.get('gross_margin') is not None:
            gm_score = min(10, max(0, ratios['gross_margin'] / 10))  # Scale 0-100% to 0-10
            analysis["profitability"]["metrics"]["gross_margin"] = {
                "value": ratios['gross_margin'],
                "score": gm_score,
                "comment": "Higher is better"
            }
            analysis["profitability"]["score"] += gm_score * 0.4  # 40% weight
        
        if ratios.get('operating_margin') is not None:
            om_score = min(10, max(0, ratios['operating_margin'] / 5))  # Scale 0-50% to 0-10
            analysis["profitability"]["metrics"]["operating_margin"] = {
                "value": ratios['operating_margin'],
                "score": om_score,
                "comment": "Higher is better"
            }
            analysis["profitability"]["score"] += om_score * 0.3  # 30% weight
        
        if ratios.get('return_on_equity') is not None:
            roe_score = min(10, max(0, ratios['return_on_equity'] / 5))  # Scale 0-50% to 0-10
            analysis["profitability"]["metrics"]["return_on_equity"] = {
                "value": ratios['return_on_equity'],
                "score": roe_score,
                "comment": "Higher is better"
            }
            analysis["profitability"]["score"] += roe_score * 0.3  # 30% weight
        
        # Analyze liquidity
        if ratios.get('current_ratio') is not None:
            cr_score = min(10, max(0, ratios['current_ratio'] * 2.5))  # Scale 0-4 to 0-10
            analysis["liquidity"]["metrics"]["current_ratio"] = {
                "value": ratios['current_ratio'],
                "score": cr_score,
                "comment": "1.5-3 is generally healthy"
            }
            analysis["liquidity"]["score"] = cr_score
        
        # Analyze leverage
        if ratios.get('debt_to_equity') is not None:
            de_score = max(0, 10 - (ratios['debt_to_equity'] * 2))  # Lower D/E is better
            analysis["leverage"]["metrics"]["debt_to_equity"] = {
                "value": ratios['debt_to_equity'],
                "score": de_score,
                "comment": "Lower is better, <2 is generally good"
            }
            analysis["leverage"]["score"] = de_score
        
        # Analyze efficiency
        if ratios.get('asset_turnover') is not None:
            at_score = min(10, ratios['asset_turnover'] * 5)  # Scale 0-2 to 0-10
            analysis["efficiency"]["metrics"]["asset_turnover"] = {
                "value": ratios['asset_turnover'],
                "score": at_score,
                "comment": "Higher is better, varies by industry"
            }
            analysis["efficiency"]["score"] = at_score
        
        # Calculate overall score (weighted average)
        weights = {
            "profitability": 0.4,
            "liquidity": 0.2,
            "leverage": 0.2,
            "efficiency": 0.2
        }
        
        total_weight = 0
        overall_score = 0
        
        for category, weight in weights.items():
            if analysis[category]["metrics"]:  # Only include if we have data
                overall_score += analysis[category]["score"] * weight
                total_weight += weight
        
        if total_weight > 0:
            analysis["overall_score"] = (overall_score / total_weight) * 10  # Scale to 0-100
        
        return analysis
    
    def _safe_divide(self, numerator: float, denominator: float) -> float:
        """Safely divide two numbers, return 0 if denominator is 0."""
        if denominator == 0:
            return 0.0
        return float(numerator) / float(denominator)
