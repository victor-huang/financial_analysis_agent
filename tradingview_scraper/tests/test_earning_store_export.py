#!/usr/bin/env python3
"""
Critical path tests for earning_store_export.py wide-format CSV row building.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from earning_store_export import build_export_rows, collect_period_columns


def make_ticker_data(
    company_name=None,
    sector=None,
    market_cap_billions=None,
    currency=None,
    revenue_quarterly=None,
    revenue_quarterly_forecast=None,
    revenue_annual=None,
    revenue_annual_forecast=None,
    eps_quarterly=None,
    eps_quarterly_forecast=None,
    eps_annual=None,
    eps_annual_forecast=None,
):
    return {
        "company_name": company_name,
        "sector": sector,
        "market_cap_billions": market_cap_billions,
        "currency": currency,
        "revenue": {
            "quarterly": revenue_quarterly or {},
            "quarterly_forecast": revenue_quarterly_forecast or {},
            "annual": revenue_annual or {},
            "annual_forecast": revenue_annual_forecast or {},
        },
        "eps": {
            "quarterly": eps_quarterly or {},
            "quarterly_forecast": eps_quarterly_forecast or {},
            "annual": eps_annual or {},
            "annual_forecast": eps_annual_forecast or {},
        },
    }


class TestCollectPeriodColumns:
    """Tests for the union-of-periods column set."""

    def test_unions_periods_across_tickers(self):
        data = {
            ("NYSE", "LLY"): make_ticker_data(revenue_quarterly={"Q1 2025": 100.0}),
            ("NASDAQ", "AAPL"): make_ticker_data(revenue_quarterly={"Q2 2025": 200.0}),
        }

        columns = collect_period_columns(data, "revenue", "quarterly")

        assert columns == ["Q1 2025", "Q2 2025"]

    def test_merges_historical_and_forecast_periods(self):
        data = {
            ("NYSE", "LLY"): make_ticker_data(
                revenue_quarterly={"Q1 2025": 100.0},
                revenue_quarterly_forecast={"Q2 2025": 110.0},
            ),
        }

        columns = collect_period_columns(data, "revenue", "quarterly")

        assert columns == ["Q1 2025", "Q2 2025"]


class TestBuildExportRows:
    """Tests for the full wide-format row builder."""

    def test_includes_static_columns_in_order(self):
        data = {
            ("NYSE", "LLY"): make_ticker_data(
                company_name="Eli Lilly and Company",
                sector="Health Technology",
                market_cap_billions=1150.0,
                currency="USD",
            ),
        }

        headers, rows = build_export_rows([("NYSE", "LLY")], data)

        assert headers[:6] == [
            "Ticker", "Exchange", "Company Name", "Market Segment", "Market Cap (B)", "Currency",
        ]
        assert rows[0][:6] == ["LLY", "NYSE", "Eli Lilly and Company", "Health Technology", "1150.00", "USD"]

    def test_period_columns_are_prefixed_by_metric(self):
        data = {
            ("NYSE", "LLY"): make_ticker_data(
                revenue_quarterly={"Q1 2025": 12730.0},
                eps_quarterly={"Q1 2025": 3.34},
            ),
        }

        headers, rows = build_export_rows([("NYSE", "LLY")], data)

        assert "Revenue Q1 2025" in headers
        assert "EPS Q1 2025" in headers

    def test_missing_period_for_one_ticker_is_blank(self):
        data = {
            ("NYSE", "LLY"): make_ticker_data(revenue_quarterly={"Q1 2025": 12730.0}),
            ("NASDAQ", "AAPL"): make_ticker_data(revenue_quarterly={"Q2 2025": 95360.0}),
        }

        headers, rows = build_export_rows([("NYSE", "LLY"), ("NASDAQ", "AAPL")], data)

        q1_idx = headers.index("Revenue Q1 2025")
        q2_idx = headers.index("Revenue Q2 2025")

        assert rows[0][q1_idx] == "12730.0"
        assert rows[0][q2_idx] == ""
        assert rows[1][q1_idx] == ""
        assert rows[1][q2_idx] == "95360.0"

    def test_missing_ticker_data_produces_blank_row(self):
        headers, rows = build_export_rows([("NYSE", "LLY")], {})

        assert rows[0][0] == "LLY"
        assert rows[0][2] == ""  # Company Name

    def test_rows_preserve_input_order(self):
        data = {
            ("NYSE", "LLY"): make_ticker_data(),
            ("NASDAQ", "AAPL"): make_ticker_data(),
        }

        headers, rows = build_export_rows([("NASDAQ", "AAPL"), ("NYSE", "LLY")], data)

        assert [row[0] for row in rows] == ["AAPL", "LLY"]
