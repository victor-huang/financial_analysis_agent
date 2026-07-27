#!/usr/bin/env python3
"""
Critical path tests for quarterly_annual_collector.py's concurrent orchestration.

_process_ticker itself drives a real Selenium scraper, so these tests mock it
out and focus on collect_for_tickers's sequential vs. concurrent aggregation.
"""

import sys
import os
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from quarterly_annual_collector import collect_for_tickers, transform_financial_data


def fake_process_ticker(ticker, headless, confirm_overwrite):
    return (ticker, {"currency": "USD"}, [f"{ticker}: merged"], [])


def _raw_data(historical=None, forecast=None):
    return {
        "currency": "USD",
        "company_name": "Steel Dynamics, Inc.",
        "sector": "Non-Energy Minerals",
        "market_cap_billions": 32.02,
        "quarterly": {"eps": {"historical": historical or [], "forecast": forecast or []}},
        "annual": {"eps": {"historical": [], "forecast": []}},
    }


class TestTransformFinancialDataForecastRetention:
    """TradingView shows the original analyst estimate alongside the reported value
    even for already-reported periods, so both must be kept rather than the estimate
    being discarded once a period is reported."""

    def test_historical_period_keeps_both_reported_and_estimate(self):
        raw = _raw_data(historical=[{"period": "Q4 '25", "reported": 1.82, "estimate": 1.7}])

        result = transform_financial_data(raw)

        assert result["eps"]["quarterly"]["Q4 2025"] == 1.82
        assert result["eps"]["quarterly_forecast"]["Q4 2025"] == 1.7

    def test_forecast_only_period_has_no_reported_value(self):
        raw = _raw_data(forecast=[{"period": "Q2 '26", "reported": None, "estimate": 3.63}])

        result = transform_financial_data(raw)

        assert "Q2 2026" not in result["eps"]["quarterly"]
        assert result["eps"]["quarterly_forecast"]["Q2 2026"] == 3.63

    def test_mixes_historical_and_forecast_only_estimates(self):
        raw = _raw_data(
            historical=[{"period": "Q4 '25", "reported": 1.82, "estimate": 1.7}],
            forecast=[{"period": "Q2 '26", "reported": None, "estimate": 3.63}],
        )

        result = transform_financial_data(raw)

        assert result["eps"]["quarterly_forecast"] == {"Q4 2025": 1.7, "Q2 2026": 3.63}


class TestCollectForTickersSequential:
    """Tests for the default concurrency=1 (sequential) path."""

    @patch("quarterly_annual_collector._process_ticker", side_effect=fake_process_ticker)
    def test_processes_all_tickers(self, mock_process):
        results = collect_for_tickers(["LLY", "AAPL"], concurrency=1)

        assert set(results.keys()) == {"LLY", "AAPL"}
        assert mock_process.call_count == 2

    @patch("quarterly_annual_collector._process_ticker", side_effect=fake_process_ticker)
    def test_skips_blank_ticker_entries(self, mock_process):
        collect_for_tickers(["LLY", "  ", ""], concurrency=1)

        called_tickers = [call.args[0] for call in mock_process.call_args_list]
        assert called_tickers == ["LLY"]


class TestCollectForTickersConcurrent:
    """Tests for the concurrency>1 (thread pool) path."""

    @patch("quarterly_annual_collector._process_ticker", side_effect=fake_process_ticker)
    def test_processes_all_tickers_concurrently(self, mock_process):
        results = collect_for_tickers(["LLY", "AAPL", "MSFT"], concurrency=3)

        assert set(results.keys()) == {"LLY", "AAPL", "MSFT"}
        assert mock_process.call_count == 3

    @patch("quarterly_annual_collector._process_ticker", side_effect=fake_process_ticker)
    def test_aggregates_merge_messages_from_all_tickers(self, mock_process):
        results = collect_for_tickers(["LLY", "AAPL"], concurrency=2)

        assert results["LLY"]["currency"] == "USD"
        assert results["AAPL"]["currency"] == "USD"

    def test_one_ticker_erroring_does_not_stop_the_others(self):
        def flaky_process(ticker, headless, confirm_overwrite):
            if ticker == "BAD":
                raise RuntimeError("scrape failed")
            return fake_process_ticker(ticker, headless, confirm_overwrite)

        with patch("quarterly_annual_collector._process_ticker", side_effect=flaky_process):
            results = collect_for_tickers(["LLY", "BAD", "AAPL"], concurrency=3)

        assert set(results.keys()) == {"LLY", "AAPL"}
        assert "BAD" not in results
