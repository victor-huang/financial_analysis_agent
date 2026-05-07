#!/usr/bin/env python3
"""
Critical path tests for financial_data_helper.py
Tests quarter mode logic and YoY data extraction with mock scraped data.
"""

import sys
import os
import re
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from financial_data_helper import FinancialDataFetcher


class MockScrapedData:
    """Factory for creating mock scraped financial data."""

    @staticmethod
    def create_quarterly_eps(
        historical_periods: list = None,
        forecast_periods: list = None
    ) -> dict:
        """Create mock quarterly EPS data structure."""
        if historical_periods is None:
            historical_periods = [
                ("Q1 '24", 1.0, 0.95),
                ("Q2 '24", 1.2, 1.15),
                ("Q3 '24", 1.4, 1.35),
                ("Q4 '24", 1.6, 1.55),
            ]
        if forecast_periods is None:
            forecast_periods = [
                ("Q1 '25", None, 1.8),
                ("Q2 '25", None, 2.0),
            ]

        historical = [
            {"period": p[0], "reported": p[1], "estimate": p[2]}
            for p in historical_periods
        ]
        forecast = [
            {"period": p[0], "reported": p[1], "estimate": p[2]}
            for p in forecast_periods
        ]

        return {"historical": historical, "forecast": forecast}

    @staticmethod
    def create_quarterly_revenue(
        historical_periods: list = None,
        forecast_periods: list = None
    ) -> dict:
        """Create mock quarterly revenue data structure (in millions)."""
        if historical_periods is None:
            historical_periods = [
                ("Q1 '24", 5000.0, 4900.0),
                ("Q2 '24", 5200.0, 5100.0),
                ("Q3 '24", 5400.0, 5300.0),
                ("Q4 '24", 5600.0, 5500.0),
            ]
        if forecast_periods is None:
            forecast_periods = [
                ("Q1 '25", None, 5800.0),
                ("Q2 '25", None, 6000.0),
            ]

        historical = [
            {"period": p[0], "reported": p[1], "estimate": p[2]}
            for p in historical_periods
        ]
        forecast = [
            {"period": p[0], "reported": p[1], "estimate": p[2]}
            for p in forecast_periods
        ]

        return {"historical": historical, "forecast": forecast}

    @staticmethod
    def create_annual_revenue(years: list = None) -> dict:
        """Create mock annual revenue data."""
        if years is None:
            years = [
                ("2022", 18000.0, 17500.0),
                ("2023", 20000.0, 19500.0),
                ("2024", 22000.0, 21500.0),
                ("2025", None, 24000.0),
            ]

        historical = [
            {"period": y[0], "reported": y[1], "estimate": y[2]}
            for y in years if y[1] is not None
        ]
        forecast = [
            {"period": y[0], "reported": y[1], "estimate": y[2]}
            for y in years if y[1] is None
        ]

        return {"historical": historical, "forecast": forecast}

    @staticmethod
    def create_annual_eps(years: list = None) -> dict:
        """Create mock annual EPS data."""
        if years is None:
            years = [
                ("2022", 4.0, 3.8),
                ("2023", 5.0, 4.8),
                ("2024", 6.0, 5.8),
                ("2025", None, 7.0),
            ]

        historical = [
            {"period": y[0], "reported": y[1], "estimate": y[2]}
            for y in years if y[1] is not None
        ]
        forecast = [
            {"period": y[0], "reported": y[1], "estimate": y[2]}
            for y in years if y[1] is None
        ]

        return {"historical": historical, "forecast": forecast}

    @staticmethod
    def create_full_scraped_data() -> dict:
        """Create complete mock scraped data structure."""
        return {
            "ticker": "TEST",
            "exchange": "NASDAQ",
            "quarterly": {
                "eps": MockScrapedData.create_quarterly_eps(),
                "revenue": MockScrapedData.create_quarterly_revenue(),
            },
            "annual": {
                "eps": MockScrapedData.create_annual_eps(),
                "revenue": MockScrapedData.create_annual_revenue(),
            },
        }


class TestQuarterModeLogic:
    """Tests for quarter mode selection logic in get_yoy_data."""

    def setup_method(self):
        self.fetcher = FinancialDataFetcher.__new__(FinancialDataFetcher)
        self.fetcher.scraper = MagicMock()
        self.fetcher.employee_scraper = MagicMock()

    @patch.object(FinancialDataFetcher, 'get_financial_data')
    @patch.object(FinancialDataFetcher, 'get_employee_data')
    def test_forecast_mode_uses_next_quarter(
        self, mock_employee, mock_financial
    ):
        """Test that forecast mode uses first forecast quarter as current quarter."""
        mock_financial.return_value = MockScrapedData.create_full_scraped_data()
        mock_employee.return_value = None

        result = self.fetcher.get_yoy_data("TEST", "NASDAQ", quarter_mode="forecast")

        assert result["current_quarter"] == "Q1 2025"

    @patch.object(FinancialDataFetcher, 'get_financial_data')
    @patch.object(FinancialDataFetcher, 'get_employee_data')
    def test_reported_mode_uses_last_historical(
        self, mock_employee, mock_financial
    ):
        """Test that reported mode uses last historical quarter as current quarter."""
        mock_financial.return_value = MockScrapedData.create_full_scraped_data()
        mock_employee.return_value = None

        result = self.fetcher.get_yoy_data("TEST", "NASDAQ", quarter_mode="reported")

        assert result["current_quarter"] == "Q4 2024"

    @patch.object(FinancialDataFetcher, 'get_financial_data')
    @patch.object(FinancialDataFetcher, 'get_employee_data')
    def test_forecast_mode_falls_back_when_no_forecast(
        self, mock_employee, mock_financial
    ):
        """Test forecast mode falls back to historical when no forecast exists."""
        data = MockScrapedData.create_full_scraped_data()
        data["quarterly"]["eps"]["forecast"] = []
        mock_financial.return_value = data
        mock_employee.return_value = None

        result = self.fetcher.get_yoy_data("TEST", "NASDAQ", quarter_mode="forecast")

        assert result["current_quarter"] == "Q4 2024"


class TestQuarterPeriodParsing:
    """Tests for quarter period string parsing (e.g., "Q4 '25" -> "Q4 2025")."""

    def test_parse_quarter_format_q4_25(self):
        """Test parsing Q4 '25 format."""
        period = "Q4 '25"
        match = re.search(r"(Q\d)\s*'(\d{2})$", period)

        assert match is not None
        quarter = match.group(1)
        year_suffix = int(match.group(2))
        full_year = 2000 + year_suffix if year_suffix < 50 else 1900 + year_suffix

        assert quarter == "Q4"
        assert full_year == 2025

    def test_parse_quarter_format_q1_99(self):
        """Test parsing old year format (should be 1999)."""
        period = "Q1 '99"
        match = re.search(r"(Q\d)\s*'(\d{2})$", period)

        assert match is not None
        year_suffix = int(match.group(2))
        full_year = 2000 + year_suffix if year_suffix < 50 else 1900 + year_suffix

        assert full_year == 1999

    def test_parse_quarter_with_no_space(self):
        """Test parsing Q4'25 format (no space)."""
        period = "Q4'25"
        match = re.search(r"(Q\d)\s*'(\d{2})$", period)

        assert match is not None
        assert match.group(1) == "Q4"


class TestYoYDataExtraction:
    """Tests for YoY (Year-over-Year) data extraction logic."""

    def setup_method(self):
        self.fetcher = FinancialDataFetcher.__new__(FinancialDataFetcher)
        self.fetcher.scraper = MagicMock()
        self.fetcher.employee_scraper = MagicMock()

    @patch.object(FinancialDataFetcher, 'get_financial_data')
    @patch.object(FinancialDataFetcher, 'get_employee_data')
    def test_extracts_eps_same_quarter_last_year(
        self, mock_employee, mock_financial
    ):
        """Test extraction of EPS from same quarter last year (4 quarters back)."""
        data = MockScrapedData.create_full_scraped_data()
        # Add more historical data to have 5+ quarters
        data["quarterly"]["eps"]["historical"] = [
            {"period": "Q1 '23", "reported": 0.5, "estimate": 0.45},
            {"period": "Q2 '23", "reported": 0.6, "estimate": 0.55},
            {"period": "Q3 '23", "reported": 0.7, "estimate": 0.65},
            {"period": "Q4 '23", "reported": 0.8, "estimate": 0.75},
            {"period": "Q1 '24", "reported": 1.0, "estimate": 0.95},
            {"period": "Q2 '24", "reported": 1.2, "estimate": 1.15},
            {"period": "Q3 '24", "reported": 1.4, "estimate": 1.35},
            {"period": "Q4 '24", "reported": 1.6, "estimate": 1.55},
        ]
        mock_financial.return_value = data
        mock_employee.return_value = None

        result = self.fetcher.get_yoy_data("TEST", "NASDAQ", quarter_mode="reported")

        # Q4 '24 reported should be 1.6
        assert result["eps_q_reported"] == 1.6
        # Same quarter last year (Q4 '23) should be 0.8
        assert result["eps_same_q_last_y"] == 0.8

    @patch.object(FinancialDataFetcher, 'get_financial_data')
    @patch.object(FinancialDataFetcher, 'get_employee_data')
    def test_extracts_annual_revenue_data(
        self, mock_employee, mock_financial
    ):
        """Test extraction of annual revenue data with correct anchor year."""
        mock_financial.return_value = MockScrapedData.create_full_scraped_data()
        mock_employee.return_value = None

        result = self.fetcher.get_yoy_data("TEST", "NASDAQ", quarter_mode="reported")

        # With Q4 '24 as current quarter, anchor year should be 2024
        assert result.get("rev_full_y_est") is not None
        assert result.get("rev_full_y_last_y") is not None

    @patch.object(FinancialDataFetcher, 'get_financial_data')
    @patch.object(FinancialDataFetcher, 'get_employee_data')
    def test_handles_missing_data_gracefully(
        self, mock_employee, mock_financial
    ):
        """Test that missing data doesn't cause errors."""
        data = {
            "ticker": "TEST",
            "exchange": "NASDAQ",
            "quarterly": {"eps": {"historical": [], "forecast": []}},
            "annual": {"eps": {"historical": [], "forecast": []}},
        }
        mock_financial.return_value = data
        mock_employee.return_value = None

        result = self.fetcher.get_yoy_data("TEST", "NASDAQ")

        assert result == {} or "current_quarter" not in result


class TestAnchorYearLogic:
    """Tests for annual data anchor year selection."""

    def setup_method(self):
        self.fetcher = FinancialDataFetcher.__new__(FinancialDataFetcher)
        self.fetcher.scraper = MagicMock()
        self.fetcher.employee_scraper = MagicMock()

    @patch.object(FinancialDataFetcher, 'get_financial_data')
    @patch.object(FinancialDataFetcher, 'get_employee_data')
    def test_anchor_year_from_quarterly_data(
        self, mock_employee, mock_financial
    ):
        """Test that anchor year is derived from current quarter."""
        data = MockScrapedData.create_full_scraped_data()
        # Set quarterly data to Q4 '25
        data["quarterly"]["eps"]["historical"] = [
            {"period": "Q4 '25", "reported": 2.0, "estimate": 1.9},
        ]
        data["quarterly"]["eps"]["forecast"] = []
        mock_financial.return_value = data
        mock_employee.return_value = None

        result = self.fetcher.get_yoy_data("TEST", "NASDAQ", quarter_mode="reported")

        # Current quarter should be Q4 2025, so anchor year should be 2025
        assert result["current_quarter"] == "Q4 2025"

    @patch.object(FinancialDataFetcher, 'get_financial_data')
    @patch.object(FinancialDataFetcher, 'get_employee_data')
    def test_rev_full_y_est_uses_current_calendar_year_when_anchor_lags(
        self, mock_employee, mock_financial
    ):
        """Rev full Y Est. should show current calendar year when anchor year is in the past.

        This covers companies (e.g. non-calendar fiscal years) whose last reported quarter
        falls in the prior calendar year, so anchor_year=2025 even though we are in 2026.
        The estimate column should still display the 2026 full-year estimate.
        """
        import datetime
        current_year = datetime.datetime.now().year

        data = MockScrapedData.create_full_scraped_data()
        # Anchor quarter is in current_year - 1 (simulates Q4 of prior year as last reported)
        prior_year = current_year - 1
        data["quarterly"]["eps"]["historical"] = [
            {"period": f"Q4 '{str(prior_year)[-2:]}", "reported": 2.0, "estimate": 1.9},
        ]
        data["quarterly"]["eps"]["forecast"] = []

        # Annual revenue: prior year is fully reported, current year has only an estimate
        prior_year_str = str(prior_year)
        curr_year_str = str(current_year)
        data["annual"]["revenue"] = {
            "historical": [
                {"period": str(prior_year - 2), "reported": 18000.0, "estimate": 17500.0},
                {"period": str(prior_year - 1), "reported": 20000.0, "estimate": 19500.0},
                {"period": prior_year_str, "reported": 22000.0, "estimate": 21500.0},
            ],
            "forecast": [
                {"period": curr_year_str, "reported": None, "estimate": 24000.0},
            ],
        }
        data["annual"]["eps"] = {
            "historical": [
                {"period": str(prior_year - 2), "reported": 4.0, "estimate": 3.8},
                {"period": str(prior_year - 1), "reported": 5.0, "estimate": 4.8},
                {"period": prior_year_str, "reported": 6.0, "estimate": 5.8},
            ],
            "forecast": [
                {"period": curr_year_str, "reported": None, "estimate": 7.0},
            ],
        }

        mock_financial.return_value = data
        mock_employee.return_value = None

        result = self.fetcher.get_yoy_data("TEST", "NASDAQ", quarter_mode="reported")

        # Rev full Y Est. must reference the CURRENT calendar year, not prior_year
        assert result.get("rev_full_y_est") == 24000.0, (
            f"Expected current year ({curr_year_str}) estimate 24000.0, "
            f"got {result.get('rev_full_y_est')}"
        )
        # Rev full Y last Y should be prior_year's reported value
        assert result.get("rev_full_y_last_y") == 22000.0
        # Rev Y 2Y ago should be two years before current year
        assert result.get("rev_y_2y_ago") == 20000.0

    @patch.object(FinancialDataFetcher, 'get_financial_data')
    @patch.object(FinancialDataFetcher, 'get_employee_data')
    def test_rev_full_y_est_stays_at_anchor_when_current_year_has_no_estimate(
        self, mock_employee, mock_financial
    ):
        """Rev full Y Est. should not upgrade to current year if no estimate exists for it."""
        import datetime
        current_year = datetime.datetime.now().year
        prior_year = current_year - 1

        data = MockScrapedData.create_full_scraped_data()
        data["quarterly"]["eps"]["historical"] = [
            {"period": f"Q4 '{str(prior_year)[-2:]}", "reported": 2.0, "estimate": 1.9},
        ]
        data["quarterly"]["eps"]["forecast"] = []

        # Annual revenue: prior year reported, current year has NO estimate
        data["annual"]["revenue"] = {
            "historical": [
                {"period": str(prior_year - 1), "reported": 20000.0, "estimate": None},
                {"period": str(prior_year), "reported": 22000.0, "estimate": 21500.0},
            ],
            "forecast": [],
        }
        data["annual"]["eps"] = {"historical": [], "forecast": []}

        mock_financial.return_value = data
        mock_employee.return_value = None

        result = self.fetcher.get_yoy_data("TEST", "NASDAQ", quarter_mode="reported")

        # No current-year estimate, so falls back to prior_year estimate
        assert result.get("rev_full_y_est") == 21500.0


class TestForecastModeEpsRevenue:
    """Tests for EPS and Revenue values in forecast mode."""

    def setup_method(self):
        self.fetcher = FinancialDataFetcher.__new__(FinancialDataFetcher)
        self.fetcher.scraper = MagicMock()
        self.fetcher.employee_scraper = MagicMock()

    @patch.object(FinancialDataFetcher, 'get_financial_data')
    @patch.object(FinancialDataFetcher, 'get_employee_data')
    def test_forecast_mode_eps_estimate_from_forecast(
        self, mock_employee, mock_financial
    ):
        """Test that forecast mode uses EPS estimate from forecast quarter."""
        mock_financial.return_value = MockScrapedData.create_full_scraped_data()
        mock_employee.return_value = None

        result = self.fetcher.get_yoy_data("TEST", "NASDAQ", quarter_mode="forecast")

        # In forecast mode, eps_q_estimate should come from first forecast (Q1 '25 = 1.8)
        assert result["eps_q_estimate"] == 1.8

    @patch.object(FinancialDataFetcher, 'get_financial_data')
    @patch.object(FinancialDataFetcher, 'get_employee_data')
    def test_forecast_mode_eps_reported_is_none(
        self, mock_employee, mock_financial
    ):
        """Test that forecast mode has None for eps_q_reported (not yet reported)."""
        mock_financial.return_value = MockScrapedData.create_full_scraped_data()
        mock_employee.return_value = None

        result = self.fetcher.get_yoy_data("TEST", "NASDAQ", quarter_mode="forecast")

        # In forecast mode, eps_q_reported should be None
        assert result["eps_q_reported"] is None

    @patch.object(FinancialDataFetcher, 'get_financial_data')
    @patch.object(FinancialDataFetcher, 'get_employee_data')
    def test_forecast_mode_same_q_last_year(
        self, mock_employee, mock_financial
    ):
        """Test that forecast mode calculates same quarter last year correctly."""
        mock_financial.return_value = MockScrapedData.create_full_scraped_data()
        mock_employee.return_value = None

        result = self.fetcher.get_yoy_data("TEST", "NASDAQ", quarter_mode="forecast")

        # Current quarter is Q1 '25 (forecast)
        # Same quarter last year is Q1 '24 which has reported=1.0
        # In default mock data, Q1 '24 is at index 0 (historical[-4])
        assert result["eps_same_q_last_y"] == 1.0

    @patch.object(FinancialDataFetcher, 'get_financial_data')
    @patch.object(FinancialDataFetcher, 'get_employee_data')
    def test_forecast_mode_revenue_estimate(
        self, mock_employee, mock_financial
    ):
        """Test that forecast mode uses revenue estimate from forecast quarter."""
        mock_financial.return_value = MockScrapedData.create_full_scraped_data()
        mock_employee.return_value = None

        result = self.fetcher.get_yoy_data("TEST", "NASDAQ", quarter_mode="forecast")

        # In forecast mode, rev_q_estimate should come from first forecast (Q1 '25 = 5800.0)
        assert result["rev_q_estimate"] == 5800.0
        # rev_q_reported should be None
        assert result["rev_q_reported"] is None

    @patch.object(FinancialDataFetcher, 'get_financial_data')
    @patch.object(FinancialDataFetcher, 'get_employee_data')
    def test_reported_mode_uses_historical(
        self, mock_employee, mock_financial
    ):
        """Test that reported mode uses last historical quarter for EPS."""
        data = MockScrapedData.create_full_scraped_data()
        # Add more historical data
        data["quarterly"]["eps"]["historical"] = [
            {"period": "Q1 '24", "reported": 1.0, "estimate": 0.95},
            {"period": "Q2 '24", "reported": 1.2, "estimate": 1.15},
            {"period": "Q3 '24", "reported": 1.4, "estimate": 1.35},
            {"period": "Q4 '24", "reported": 1.6, "estimate": 1.55},
        ]
        mock_financial.return_value = data
        mock_employee.return_value = None

        result = self.fetcher.get_yoy_data("TEST", "NASDAQ", quarter_mode="reported")

        # In reported mode, eps_q_estimate and eps_q_reported come from last historical
        assert result["eps_q_estimate"] == 1.55
        assert result["eps_q_reported"] == 1.6
