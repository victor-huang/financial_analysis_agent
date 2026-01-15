#!/usr/bin/env python3
"""
Helper functions for calculating financial metrics and percentages.
"""

from typing import Optional


def calculate_beat_percentage(actual: Optional[float], estimate: Optional[float]) -> Optional[float]:
    """
    Calculate beat percentage: ((actual - estimate) / estimate) * 100
    
    Args:
        actual: Actual reported value
        estimate: Estimated value
    
    Returns:
        Beat percentage or None if calculation not possible
    """
    if actual is None or estimate is None or estimate == 0:
        return None
    
    return ((actual - estimate) / abs(estimate)) * 100


def calculate_yoy_percentage(current: Optional[float], last_year: Optional[float]) -> Optional[float]:
    """
    Calculate year-over-year percentage: ((current - last_year) / last_year) * 100
    
    Args:
        current: Current period value
        last_year: Same period last year value
    
    Returns:
        YoY percentage or None if calculation not possible
    """
    if current is None or last_year is None or last_year == 0:
        return None
    
    return ((current - last_year) / abs(last_year)) * 100


def format_market_cap(market_cap: Optional[float]) -> str:
    """
    Format market cap in billions.
    
    Args:
        market_cap: Market cap value (in base units)
    
    Returns:
        Formatted string (e.g., "123.45B") or empty string
    """
    if market_cap is None:
        return ""
    
    # Market cap from API is typically in base currency
    # Convert to billions
    billions = market_cap / 1_000_000_000
    return f"{billions:.2f}"


def format_revenue(revenue: Optional[float]) -> str:
    """
    Format revenue value.
    
    Args:
        revenue: Revenue value (in millions from scraper)
    
    Returns:
        Formatted string or empty
    """
    if revenue is None:
        return ""
    
    # Revenue from scraper is in millions
    billions = revenue / 1000
    return f"{billions:.2f}B"


def format_percentage(value: Optional[float]) -> str:
    """
    Format percentage value.
    
    Args:
        value: Percentage value
    
    Returns:
        Formatted string (e.g., "12.34%") or empty
    """
    if value is None:
        return ""
    
    return f"{value:.2f}%"


def format_number(value: Optional[float], decimals: int = 2) -> str:
    """
    Format number with specified decimals.
    
    Args:
        value: Number to format
        decimals: Number of decimal places
    
    Returns:
        Formatted string or empty
    """
    if value is None:
        return ""
    
    return f"{value:.{decimals}f}"
