#!/usr/bin/env python3
"""
Critical path tests for metrics_calculator.py
Tests financial metric calculations and formatting.
"""

import sys
import os
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from metrics_calculator import (
    calculate_beat_percentage,
    calculate_yoy_percentage,
    format_market_cap,
    format_revenue,
    format_percentage,
    format_number,
)


class TestCalculateBeatPercentage:
    """Tests for EPS/Revenue beat percentage calculation."""

    def test_positive_beat(self):
        """Test positive beat (actual > estimate)."""
        result = calculate_beat_percentage(actual=1.10, estimate=1.00)
        assert result == pytest.approx(10.0)

    def test_negative_beat_miss(self):
        """Test negative beat/miss (actual < estimate)."""
        result = calculate_beat_percentage(actual=0.90, estimate=1.00)
        assert result == pytest.approx(-10.0)

    def test_exact_match(self):
        """Test exact match (0% beat)."""
        result = calculate_beat_percentage(actual=1.00, estimate=1.00)
        assert result == pytest.approx(0.0)

    def test_none_actual_returns_none(self):
        """Test that None actual returns None."""
        result = calculate_beat_percentage(actual=None, estimate=1.00)
        assert result is None

    def test_none_estimate_returns_none(self):
        """Test that None estimate returns None."""
        result = calculate_beat_percentage(actual=1.00, estimate=None)
        assert result is None

    def test_zero_estimate_returns_none(self):
        """Test that zero estimate returns None (avoid division by zero)."""
        result = calculate_beat_percentage(actual=1.00, estimate=0)
        assert result is None

    def test_negative_estimate_uses_absolute(self):
        """Test that negative estimate uses absolute value for denominator."""
        result = calculate_beat_percentage(actual=-0.50, estimate=-1.00)
        # (-0.50 - (-1.00)) / abs(-1.00) * 100 = 0.50 / 1.00 * 100 = 50%
        assert result == pytest.approx(50.0)


class TestCalculateYoYPercentage:
    """Tests for Year-over-Year percentage calculation."""

    def test_positive_growth(self):
        """Test positive YoY growth."""
        result = calculate_yoy_percentage(current=110.0, last_year=100.0)
        assert result == pytest.approx(10.0)

    def test_negative_growth(self):
        """Test negative YoY growth (decline)."""
        result = calculate_yoy_percentage(current=90.0, last_year=100.0)
        assert result == pytest.approx(-10.0)

    def test_no_change(self):
        """Test no change (0% growth)."""
        result = calculate_yoy_percentage(current=100.0, last_year=100.0)
        assert result == pytest.approx(0.0)

    def test_none_current_returns_none(self):
        """Test that None current returns None."""
        result = calculate_yoy_percentage(current=None, last_year=100.0)
        assert result is None

    def test_none_last_year_returns_none(self):
        """Test that None last_year returns None."""
        result = calculate_yoy_percentage(current=100.0, last_year=None)
        assert result is None

    def test_zero_last_year_returns_none(self):
        """Test that zero last_year returns None."""
        result = calculate_yoy_percentage(current=100.0, last_year=0)
        assert result is None

    def test_negative_to_positive_turnaround(self):
        """Test turnaround from negative to positive."""
        result = calculate_yoy_percentage(current=50.0, last_year=-50.0)
        # (50 - (-50)) / abs(-50) * 100 = 100 / 50 * 100 = 200%
        assert result == pytest.approx(200.0)


class TestFormatMarketCap:
    """Tests for market cap formatting."""

    def test_format_billions(self):
        """Test formatting market cap in billions."""
        result = format_market_cap(50000000000)  # 50B
        assert result == "50.00"

    def test_format_small_cap(self):
        """Test formatting smaller market cap."""
        result = format_market_cap(500000000)  # 500M = 0.5B
        assert result == "0.50"

    def test_none_returns_empty(self):
        """Test that None returns empty string."""
        result = format_market_cap(None)
        assert result == ""


class TestFormatRevenue:
    """Tests for revenue formatting (in millions)."""

    def test_format_revenue_millions(self):
        """Test formatting revenue already in millions."""
        result = format_revenue(5000.0)
        assert result == "5000.0"

    def test_format_revenue_decimal(self):
        """Test formatting revenue with decimals."""
        result = format_revenue(5123.456)
        assert result == "5123.456"

    def test_none_returns_empty(self):
        """Test that None returns empty string."""
        result = format_revenue(None)
        assert result == ""


class TestFormatPercentage:
    """Tests for percentage formatting."""

    def test_format_positive_percentage(self):
        """Test formatting positive percentage."""
        result = format_percentage(12.345)
        assert result == "12.35%"

    def test_format_negative_percentage(self):
        """Test formatting negative percentage."""
        result = format_percentage(-5.678)
        assert result == "-5.68%"

    def test_format_zero_percentage(self):
        """Test formatting zero percentage."""
        result = format_percentage(0.0)
        assert result == "0.00%"

    def test_none_returns_empty(self):
        """Test that None returns empty string."""
        result = format_percentage(None)
        assert result == ""


class TestFormatNumber:
    """Tests for general number formatting."""

    def test_format_default_decimals(self):
        """Test formatting with default 2 decimals."""
        result = format_number(1.2345)
        assert result == "1.23"

    def test_format_custom_decimals(self):
        """Test formatting with custom decimal places."""
        result = format_number(1.2346, decimals=3)
        assert result == "1.235"

    def test_format_zero_decimals(self):
        """Test formatting with 0 decimal places."""
        result = format_number(1.9, decimals=0)
        assert result == "2"

    def test_format_negative_number(self):
        """Test formatting negative number."""
        result = format_number(-1.5)
        assert result == "-1.50"

    def test_none_returns_empty(self):
        """Test that None returns empty string."""
        result = format_number(None)
        assert result == ""
