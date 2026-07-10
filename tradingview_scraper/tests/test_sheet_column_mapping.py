#!/usr/bin/env python3
"""
Critical path tests for sheet_column_mapping.py header parsing.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from sheet_column_mapping import parse_header_cell, build_rows_for_headers

# The real "ERN DataBase" header, captured verbatim (including its typos:
# a trailing space on "Q1 26 Rev " and inconsistent "act" vs "act." punctuation).
ERN_DATABASE_HEADER = [
    "ticker", "Company name", "Market segment", "Market Cap (B)",
    "Q2 24 EPS", "Q2 24 Rev", "Q3 24 EPS", "Q3 24 Rev", "Q4 24 EPS", "Q4 24 Rev",
    "2024 EPS", "2024 Rev",
    "Q1 25 EPS", "Q1 25 Rev", "Q2 25 EPS", "Q2 25 Rev", "Q3 25 EPS", "Q3 25 Rev", "Q4 25 EPS", "Q4 25 Rev",
    "2025 EPS", "2025 Rev",
    "Q1 26 EPS", "Q1 26 Rev ",
    "Q2 26 EPS Est.", "Q2 26 EPS act", "Q2 26 Rev Est.", "Q2 26 Rev act.",
    "2026 Est EPS", "2026 Est Rev",
]


class TestParseStaticFields:
    """Tests for static profile field header parsing."""

    def test_recognizes_ticker(self):
        assert parse_header_cell("ticker") is not None

    def test_recognizes_company_name(self):
        assert parse_header_cell("Company name") is not None

    def test_recognizes_market_segment_as_sector(self):
        resolver = parse_header_cell("Market segment")
        data = {"sector": "Non-Energy Minerals"}
        assert resolver(data, "STLD", "NASDAQ") == "Non-Energy Minerals"

    def test_recognizes_market_cap(self):
        resolver = parse_header_cell("Market Cap (B)")
        data = {"market_cap_billions": 32.02}
        assert resolver(data, "STLD", "NASDAQ") == "32.02"

    def test_unrecognized_header_returns_none(self):
        assert parse_header_cell("Some Random Column") is None


class TestParseQuarterlyHeaders:
    """Tests for quarterly EPS/Rev header parsing, including real-world quirks."""

    def test_plain_quarter_eps_resolves_from_historical(self):
        resolver = parse_header_cell("Q3 24 EPS")
        data = {"eps": {"quarterly": {"Q3 2024": 2.05}, "quarterly_forecast": {}}}
        assert resolver(data, "STLD", "NASDAQ") == "2.05"

    def test_trailing_space_in_header_is_tolerated(self):
        resolver = parse_header_cell("Q1 26 Rev ")
        data = {"revenue": {"quarterly": {"Q1 2026": 5200.0}, "quarterly_forecast": {}}}
        assert resolver(data, "STLD", "NASDAQ") == "5200.0"

    def test_est_suffix_reads_forecast_bucket(self):
        resolver = parse_header_cell("Q2 26 EPS Est.")
        data = {"eps": {"quarterly": {}, "quarterly_forecast": {"Q2 2026": 3.69}}}
        assert resolver(data, "STLD", "NASDAQ") == "3.69"

    def test_act_suffix_without_period_reads_historical_bucket(self):
        resolver = parse_header_cell("Q2 26 EPS act")
        data = {"eps": {"quarterly": {"Q2 2026": 3.75}, "quarterly_forecast": {"Q2 2026": 3.69}}}
        assert resolver(data, "STLD", "NASDAQ") == "3.75"

    def test_act_suffix_with_period_reads_historical_bucket(self):
        resolver = parse_header_cell("Q2 26 Rev act.")
        data = {"revenue": {"quarterly": {"Q2 2026": 5700.0}, "quarterly_forecast": {"Q2 2026": 5570.0}}}
        assert resolver(data, "STLD", "NASDAQ") == "5700.0"

    def test_act_bucket_blank_when_not_yet_reported(self):
        resolver = parse_header_cell("Q2 26 EPS act")
        data = {"eps": {"quarterly": {}, "quarterly_forecast": {"Q2 2026": 3.69}}}
        assert resolver(data, "STLD", "NASDAQ") == ""

    def test_two_digit_year_expands_to_current_century(self):
        resolver = parse_header_cell("Q3 24 EPS")
        data = {"eps": {"quarterly": {"Q3 2024": 2.05}, "quarterly_forecast": {}}}
        assert resolver(data, "STLD", "NASDAQ") == "2.05"


class TestParseAnnualHeaders:
    """Tests for annual EPS/Rev header parsing."""

    def test_plain_year_resolves_from_historical(self):
        resolver = parse_header_cell("2024 EPS")
        data = {"eps": {"annual": {"2024 Yearly": 9.84}, "annual_forecast": {}}}
        assert resolver(data, "STLD", "NASDAQ") == "9.84"

    def test_est_prefixed_year_resolves_from_forecast(self):
        resolver = parse_header_cell("2026 Est EPS")
        data = {"eps": {"annual": {}, "annual_forecast": {"2026 Yearly": 16.44}}}
        assert resolver(data, "STLD", "NASDAQ") == "16.44"

    def test_est_prefixed_revenue_resolves_from_forecast(self):
        resolver = parse_header_cell("2026 Est Rev")
        data = {"revenue": {"annual": {}, "annual_forecast": {"2026 Yearly": 22600.0}}}
        assert resolver(data, "STLD", "NASDAQ") == "22600.0"


class TestBuildRowsForHeaders:
    """Tests for the full row-building pass against the real ERN DataBase header."""

    def test_every_ern_database_header_maps_except_none(self):
        _, unrecognized = build_rows_for_headers(ERN_DATABASE_HEADER, [], {})
        assert unrecognized == []

    def test_builds_row_matching_static_and_period_fields(self):
        data = {
            ("NASDAQ", "STLD"): {
                "company_name": "Steel Dynamics, Inc.",
                "sector": "Non-Energy Minerals",
                "market_cap_billions": 32.02,
                "revenue": {"quarterly": {"Q3 2024": 4340.0}, "quarterly_forecast": {}, "annual": {}, "annual_forecast": {}},
                "eps": {"quarterly": {"Q3 2024": 2.05}, "quarterly_forecast": {}, "annual": {}, "annual_forecast": {}},
            }
        }

        rows, _ = build_rows_for_headers(
            ["ticker", "Company name", "Q3 24 EPS", "Q3 24 Rev"],
            [("NASDAQ", "STLD")],
            data,
        )

        assert rows == [["STLD", "Steel Dynamics, Inc.", "2.05", "4340.0"]]

    def test_missing_ticker_data_yields_blank_cells(self):
        rows, _ = build_rows_for_headers(["ticker", "Q3 24 EPS"], [("NASDAQ", "STLD")], {})
        assert rows == [["STLD", ""]]
