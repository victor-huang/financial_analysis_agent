#!/usr/bin/env python3
"""
Critical path tests for quarterly_annual_collector.py's concurrent orchestration.

_process_ticker itself drives a real Selenium scraper, so these tests mock it
out and focus on collect_for_tickers's sequential vs. concurrent aggregation.
"""

import sys
import os
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from quarterly_annual_collector import collect_for_tickers, transform_financial_data, resolve_exchange


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


def _mock_requests_get(symbols, working_exchanges):
    """
    Build a requests.get side_effect that answers both calls resolve_exchange
    makes: the symbol search call (returns symbols as JSON) and the forecast
    page verification call for each exchange guess (200 if the exchange is in
    working_exchanges, 404 otherwise).
    """

    def side_effect(url, *args, **kwargs):
        response = MagicMock()
        if "symbol-search" in url:
            response.json.return_value = {"symbols": symbols}
            response.raise_for_status.return_value = None
        else:
            exchange = url.split("/symbols/")[1].split("-")[0].replace("%20", " ")
            response.status_code = 200 if exchange in working_exchanges else 404
        return response

    return side_effect


class TestResolveExchange:
    """Tests for resolving a ticker's exchange, including TradingView's search-API
    vs. page-routing exchange mismatches (see PRK)."""

    def test_returns_none_when_no_us_candidates(self):
        with patch(
            "quarterly_annual_collector.requests.get",
            side_effect=_mock_requests_get([{"symbol": "LLY", "exchange": "NYSE", "country": "CA"}], []),
        ):
            assert resolve_exchange("LLY") is None

    def test_prefers_exact_preferred_exchange_match(self):
        symbols = [{"symbol": "LLY", "exchange": "NYSE", "country": "US"}]
        with patch(
            "quarterly_annual_collector.requests.get",
            side_effect=_mock_requests_get(symbols, working_exchanges={"NYSE"}),
        ):
            assert resolve_exchange("LLY") == "NYSE"

    def test_prefers_verified_well_known_exchange_over_unverified_search_result(self):
        """Regression test for PRK: the search API reported "NYSE Arca" (unverified,
        404s) and "BOATS" (an obscure alternate venue, but verified/200), while the
        well-known "AMEX" exchange also works. AMEX should win over BOATS."""
        symbols = [
            {"symbol": "PRK", "exchange": "NYSE Arca", "country": "US"},
            {"symbol": "PRK", "exchange": "BOATS", "country": "US"},
        ]
        with patch(
            "quarterly_annual_collector.requests.get",
            side_effect=_mock_requests_get(symbols, working_exchanges={"BOATS", "AMEX"}),
        ):
            assert resolve_exchange("PRK") == "AMEX"

    def test_falls_back_to_obscure_exchange_when_nothing_well_known_works(self):
        symbols = [{"symbol": "PRK", "exchange": "BOATS", "country": "US"}]
        with patch(
            "quarterly_annual_collector.requests.get",
            side_effect=_mock_requests_get(symbols, working_exchanges={"BOATS"}),
        ):
            assert resolve_exchange("PRK") == "BOATS"

    def test_returns_none_when_no_candidate_forecast_page_exists(self):
        symbols = [{"symbol": "PRK", "exchange": "NYSE Arca", "country": "US"}]
        with patch(
            "quarterly_annual_collector.requests.get",
            side_effect=_mock_requests_get(symbols, working_exchanges=set()),
        ):
            assert resolve_exchange("PRK") is None


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
