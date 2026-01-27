#!/usr/bin/env python3
"""
Critical path tests for csv_generator.py
Tests CSV row building and formatting with mock data.
"""

import sys
import os
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from csv_generator import build_csv_row, get_csv_headers, save_to_csv


class MockApiData:
    """Factory for creating mock API data."""

    @staticmethod
    def create_earnings_api_data(
        ticker: str = "TEST",
        exchange: str = "NASDAQ",
        company_name: str = "Test Company Inc.",
        eps_estimate: float = 1.5,
        eps_actual: float = 1.6,
        revenue_estimate: float = 5000000000,  # 5B in base units
        revenue_actual: float = 5200000000,    # 5.2B in base units
        market_cap: float = 50000000000,       # 50B
        sector: str = "Technology"
    ) -> dict:
        return {
            "ticker": ticker,
            "exchange": exchange,
            "company_name": company_name,
            "eps_q_estimate": eps_estimate,
            "eps_q_actual": eps_actual,
            "revenue_q_estimate": revenue_estimate,
            "revenue_q_actual": revenue_actual,
            "market_cap": market_cap,
            "sector": sector,
        }


class MockYoYData:
    """Factory for creating mock YoY scraped data."""

    @staticmethod
    def create_yoy_data(
        current_quarter: str = "Q1 2025",
        eps_same_q_last_y: float = 1.2,
        rev_same_q_last_y: float = 4500.0,  # In millions
        rev_last_q: float = 5000.0,
        rev_last_q_last_y: float = 4300.0,
        rev_full_y_est: float = 21000.0,
        rev_full_y_last_y: float = 19000.0,
        rev_y_2y_ago: float = 17000.0
    ) -> dict:
        return {
            "current_quarter": current_quarter,
            "eps_same_q_last_y": eps_same_q_last_y,
            "rev_same_q_last_y": rev_same_q_last_y,
            "rev_last_q": rev_last_q,
            "rev_last_q_last_y": rev_last_q_last_y,
            "rev_full_y_est": rev_full_y_est,
            "rev_full_y_last_y": rev_full_y_last_y,
            "rev_y_2y_ago": rev_y_2y_ago,
        }


class TestGetCsvHeaders:
    """Tests for CSV header generation."""

    def test_headers_include_current_quarter(self):
        """Test that Current Quarter column is in headers."""
        headers = get_csv_headers()
        assert "Current Quarter" in headers

    def test_headers_order_current_quarter_before_eps(self):
        """Test that Current Quarter comes before EPS Q Est."""
        headers = get_csv_headers()
        current_q_idx = headers.index("Current Quarter")
        eps_q_idx = headers.index("EPS Q Est.")
        assert current_q_idx < eps_q_idx

    def test_headers_count(self):
        """Test expected number of headers."""
        headers = get_csv_headers()
        assert len(headers) == 18  # Current count of columns


class TestBuildCsvRow:
    """Tests for CSV row building."""

    def test_builds_row_with_all_data(self):
        """Test building a complete row with all data present."""
        api_data = MockApiData.create_earnings_api_data()
        yoy_data = MockYoYData.create_yoy_data()

        row = build_csv_row(api_data, yoy_data)

        assert row["ticker"] == "TEST"
        assert row["Company name"] == "Test Company Inc."
        assert row["Current Quarter"] == "Q1 2025"
        assert row["EPS Q Est."] == "1.50"
        assert row["EPS Q actual"] == "1.60"

    def test_market_cap_formatted_in_billions(self):
        """Test that market cap is formatted in billions."""
        api_data = MockApiData.create_earnings_api_data(market_cap=50000000000)
        yoy_data = MockYoYData.create_yoy_data()

        row = build_csv_row(api_data, yoy_data)

        assert row["Market Cap (B)"] == "50.00"

    def test_revenue_converted_to_millions(self):
        """Test that API revenue (base units) is converted to millions."""
        api_data = MockApiData.create_earnings_api_data(
            revenue_estimate=5000000000,  # 5B
            revenue_actual=5200000000     # 5.2B
        )
        yoy_data = MockYoYData.create_yoy_data()

        row = build_csv_row(api_data, yoy_data)

        # Should be in millions: 5000.0 and 5200.0
        assert row["Rev Q est."] == "5000.0"
        assert row["Rev Q actual"] == "5200.0"

    def test_handles_missing_yoy_data(self):
        """Test that missing YoY data results in empty strings."""
        api_data = MockApiData.create_earnings_api_data()
        yoy_data = {}  # No YoY data

        row = build_csv_row(api_data, yoy_data)

        assert row["ticker"] == "TEST"
        assert row["Current Quarter"] == ""
        assert row["EPS same Q last Y"] == ""
        assert row["Rev same Q last Y"] == ""

    def test_handles_none_values(self):
        """Test that None values are converted to empty strings."""
        api_data = MockApiData.create_earnings_api_data(
            eps_actual=None,
            revenue_actual=None
        )
        yoy_data = MockYoYData.create_yoy_data()

        row = build_csv_row(api_data, yoy_data)

        assert row["EPS Q actual"] == ""
        assert row["Rev Q actual"] == ""

    def test_preserves_hot_and_note_columns(self):
        """Test that hot? and Note columns are empty by default."""
        api_data = MockApiData.create_earnings_api_data()
        yoy_data = MockYoYData.create_yoy_data()

        row = build_csv_row(api_data, yoy_data)

        assert row["hot?"] == ""
        assert row["Note"] == ""

    def test_prefers_yoy_eps_estimate_over_api(self):
        """Test that yoy_data EPS estimate is preferred over api_data."""
        api_data = MockApiData.create_earnings_api_data(eps_estimate=1.50)
        yoy_data = MockYoYData.create_yoy_data()
        yoy_data["eps_q_estimate"] = 1.28  # Should override api_data

        row = build_csv_row(api_data, yoy_data)

        assert row["EPS Q Est."] == "1.28"

    def test_prefers_yoy_eps_reported_over_api(self):
        """Test that yoy_data EPS reported is preferred over api_data."""
        api_data = MockApiData.create_earnings_api_data(eps_actual=1.60)
        yoy_data = MockYoYData.create_yoy_data()
        yoy_data["eps_q_reported"] = 1.55  # Should override api_data

        row = build_csv_row(api_data, yoy_data)

        assert row["EPS Q actual"] == "1.55"

    def test_forecast_mode_eps_reported_none(self):
        """Test forecast mode where eps_q_reported is None (quarter not reported yet)."""
        api_data = MockApiData.create_earnings_api_data(eps_actual=1.60)
        yoy_data = MockYoYData.create_yoy_data()
        yoy_data["eps_q_estimate"] = 1.28
        yoy_data["eps_q_reported"] = None  # Forecast mode - not reported yet

        row = build_csv_row(api_data, yoy_data)

        assert row["EPS Q Est."] == "1.28"
        assert row["EPS Q actual"] == ""  # Should be empty, not api_data value

    def test_prefers_yoy_revenue_estimate_over_api(self):
        """Test that yoy_data revenue estimate is preferred over api_data."""
        api_data = MockApiData.create_earnings_api_data(revenue_estimate=5000000000)
        yoy_data = MockYoYData.create_yoy_data()
        yoy_data["rev_q_estimate"] = 4430.0  # Already in millions

        row = build_csv_row(api_data, yoy_data)

        assert row["Rev Q est."] == "4430.0"

    def test_forecast_mode_revenue_reported_none(self):
        """Test forecast mode where rev_q_reported is None (quarter not reported yet)."""
        api_data = MockApiData.create_earnings_api_data(revenue_actual=5200000000)
        yoy_data = MockYoYData.create_yoy_data()
        yoy_data["rev_q_estimate"] = 4430.0
        yoy_data["rev_q_reported"] = None  # Forecast mode - not reported yet

        row = build_csv_row(api_data, yoy_data)

        assert row["Rev Q est."] == "4430.0"
        assert row["Rev Q actual"] == ""  # Should be empty, not api_data value

    def test_falls_back_to_api_when_yoy_missing(self):
        """Test fallback to api_data when yoy_data doesn't have the values."""
        api_data = MockApiData.create_earnings_api_data(
            eps_estimate=1.50,
            eps_actual=1.60,
            revenue_estimate=5000000000,
            revenue_actual=5200000000
        )
        yoy_data = MockYoYData.create_yoy_data()
        # yoy_data doesn't have eps_q_estimate, eps_q_reported, rev_q_estimate, rev_q_reported

        row = build_csv_row(api_data, yoy_data)

        # Should fall back to api_data
        assert row["EPS Q Est."] == "1.50"
        assert row["EPS Q actual"] == "1.60"
        assert row["Rev Q est."] == "5000.0"  # Converted from base units to millions
        assert row["Rev Q actual"] == "5200.0"


class TestSaveToCsv:
    """Tests for CSV file saving."""

    def test_saves_rows_to_file(self):
        """Test that rows are saved correctly to CSV file."""
        api_data = MockApiData.create_earnings_api_data()
        yoy_data = MockYoYData.create_yoy_data()
        row = build_csv_row(api_data, yoy_data)

        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            filename = f.name

        try:
            save_to_csv([row], filename)

            with open(filename, 'r') as f:
                content = f.read()

            assert "ticker" in content
            assert "TEST" in content
            assert "Q1 2025" in content
        finally:
            os.unlink(filename)

    def test_handles_empty_data(self):
        """Test that empty data list doesn't crash."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            filename = f.name

        try:
            save_to_csv([], filename)
            # Should not raise an error
        finally:
            if os.path.exists(filename):
                os.unlink(filename)

    def test_multiple_rows_preserve_order(self):
        """Test that multiple rows maintain their order."""
        rows = []
        for i, ticker in enumerate(["AAA", "BBB", "CCC"]):
            api_data = MockApiData.create_earnings_api_data(ticker=ticker)
            yoy_data = MockYoYData.create_yoy_data()
            rows.append(build_csv_row(api_data, yoy_data))

        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            filename = f.name

        try:
            save_to_csv(rows, filename)

            with open(filename, 'r') as f:
                lines = f.readlines()

            # Check order (header + 3 data rows)
            assert len(lines) == 4
            assert "AAA" in lines[1]
            assert "BBB" in lines[2]
            assert "CCC" in lines[3]
        finally:
            os.unlink(filename)
