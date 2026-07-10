#!/usr/bin/env python3
"""
Critical path tests for earnings_data_store.py merge logic.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from earnings_data_store import merge_ticker_data, _label_sort_key


def empty_store():
    return {
        "currency": None,
        "revenue": {"quarterly": {}, "annual": {}, "quarterly_forecast": {}, "annual_forecast": {}},
        "eps": {"quarterly": {}, "annual": {}, "quarterly_forecast": {}, "annual_forecast": {}},
    }


class TestLabelSortKey:
    """Tests for chronological sort key parsing of display labels."""

    def test_sorts_quarterly_labels_by_year_then_quarter(self):
        labels = ["Q3 2025", "Q1 2024", "Q1 2025"]
        assert sorted(labels, key=_label_sort_key) == ["Q1 2024", "Q1 2025", "Q3 2025"]

    def test_sorts_annual_labels_by_year(self):
        labels = ["2025 Yearly", "2021 Yearly", "2023 Yearly"]
        assert sorted(labels, key=_label_sort_key) == ["2021 Yearly", "2023 Yearly", "2025 Yearly"]

    def test_unrecognized_label_sorts_last(self):
        labels = ["2025 Yearly", "garbage"]
        assert sorted(labels, key=_label_sort_key) == ["2025 Yearly", "garbage"]


class TestMergeNewData:
    """Tests for merging into an empty store (first run)."""

    def test_adds_all_reported_and_forecast_points(self):
        existing = empty_store()
        incoming = {
            "currency": "USD",
            "revenue": {
                "quarterly": {"Q1 2025": 100.0},
                "annual": {"2025 Yearly": 400.0},
                "quarterly_forecast": {"Q2 2025": 110.0},
                "annual_forecast": {"2026 Yearly": 450.0},
            },
            "eps": {
                "quarterly": {"Q1 2025": 1.0},
                "annual": {"2025 Yearly": 4.0},
                "quarterly_forecast": {"Q2 2025": 1.1},
                "annual_forecast": {"2026 Yearly": 4.5},
            },
        }

        merged, log = merge_ticker_data("TEST", existing, incoming, confirm_overwrite=lambda *a: True)

        assert merged["currency"] == "USD"
        assert merged["revenue"]["quarterly"] == {"Q1 2025": 100.0}
        assert merged["revenue"]["quarterly_forecast"] == {"Q2 2025": 110.0}
        assert any("added new revenue quarterly" in m for m in log)


class TestMergeReportedConflicts:
    """Tests for conflicting reported (actual) data points."""

    def test_no_conflict_when_values_match(self):
        existing = empty_store()
        existing["revenue"]["quarterly"]["Q1 2025"] = 100.0
        incoming = {"currency": None, "revenue": {"quarterly": {"Q1 2025": 100.0}, "annual": {}, "quarterly_forecast": {}, "annual_forecast": {}}, "eps": {"quarterly": {}, "annual": {}, "quarterly_forecast": {}, "annual_forecast": {}}}

        merged, log = merge_ticker_data("TEST", existing, incoming, confirm_overwrite=lambda *a: True)

        assert merged["revenue"]["quarterly"]["Q1 2025"] == 100.0
        assert not any("OVERWROTE" in m or "KEPT" in m for m in log)

    def test_confirmed_overwrite_updates_value(self):
        existing = empty_store()
        existing["revenue"]["quarterly"]["Q1 2025"] = 100.0
        incoming = {"currency": None, "revenue": {"quarterly": {"Q1 2025": 105.0}, "annual": {}, "quarterly_forecast": {}, "annual_forecast": {}}, "eps": {"quarterly": {}, "annual": {}, "quarterly_forecast": {}, "annual_forecast": {}}}

        merged, log = merge_ticker_data("TEST", existing, incoming, confirm_overwrite=lambda *a: True)

        assert merged["revenue"]["quarterly"]["Q1 2025"] == 105.0
        assert any("OVERWROTE" in m for m in log)

    def test_declined_overwrite_keeps_stored_value(self):
        existing = empty_store()
        existing["revenue"]["quarterly"]["Q1 2025"] = 100.0
        incoming = {"currency": None, "revenue": {"quarterly": {"Q1 2025": 105.0}, "annual": {}, "quarterly_forecast": {}, "annual_forecast": {}}, "eps": {"quarterly": {}, "annual": {}, "quarterly_forecast": {}, "annual_forecast": {}}}

        merged, log = merge_ticker_data("TEST", existing, incoming, confirm_overwrite=lambda *a: False)

        assert merged["revenue"]["quarterly"]["Q1 2025"] == 100.0
        assert any("KEPT existing" in m for m in log)

    def test_confirm_overwrite_receives_context(self):
        existing = empty_store()
        existing["revenue"]["quarterly"]["Q1 2025"] = 100.0
        incoming = {"currency": None, "revenue": {"quarterly": {"Q1 2025": 105.0}, "annual": {}, "quarterly_forecast": {}, "annual_forecast": {}}, "eps": {"quarterly": {}, "annual": {}, "quarterly_forecast": {}, "annual_forecast": {}}}

        received = {}

        def capture(ticker, metric, bucket, period, old_value, new_value):
            received.update(
                ticker=ticker, metric=metric, bucket=bucket,
                period=period, old_value=old_value, new_value=new_value,
            )
            return True

        merge_ticker_data("TEST", existing, incoming, confirm_overwrite=capture)

        assert received == {
            "ticker": "TEST", "metric": "revenue", "bucket": "quarterly",
            "period": "Q1 2025", "old_value": 100.0, "new_value": 105.0,
        }


class TestMergeForecast:
    """Tests for forecast buckets, which auto-overwrite."""

    def test_forecast_conflict_overwrites_without_confirmation(self):
        existing = empty_store()
        existing["revenue"]["quarterly_forecast"]["Q2 2025"] = 110.0
        incoming = {"currency": None, "revenue": {"quarterly": {}, "annual": {}, "quarterly_forecast": {"Q2 2025": 120.0}, "annual_forecast": {}}, "eps": {"quarterly": {}, "annual": {}, "quarterly_forecast": {}, "annual_forecast": {}}}

        def never_called(*args):
            raise AssertionError("confirm_overwrite should not be called for forecast data")

        merged, log = merge_ticker_data("TEST", existing, incoming, confirm_overwrite=never_called)

        assert merged["revenue"]["quarterly_forecast"]["Q2 2025"] == 120.0
        assert any("forecast updated" in m for m in log)

    def test_stale_forecast_removed_once_reported(self):
        existing = empty_store()
        existing["revenue"]["quarterly_forecast"]["Q2 2025"] = 110.0
        incoming = {
            "currency": None,
            "revenue": {"quarterly": {"Q2 2025": 112.0}, "annual": {}, "quarterly_forecast": {}, "annual_forecast": {}},
            "eps": {"quarterly": {}, "annual": {}, "quarterly_forecast": {}, "annual_forecast": {}},
        }

        merged, log = merge_ticker_data("TEST", existing, incoming, confirm_overwrite=lambda *a: True)

        assert "Q2 2025" not in merged["revenue"]["quarterly_forecast"]
        assert merged["revenue"]["quarterly"]["Q2 2025"] == 112.0
        assert any("removed stale revenue quarterly_forecast" in m for m in log)


class TestMergeCurrency:
    """Tests for currency merge behavior."""

    def test_records_currency_when_previously_unknown(self):
        existing = empty_store()
        incoming = {"currency": "USD", "revenue": {"quarterly": {}, "annual": {}, "quarterly_forecast": {}, "annual_forecast": {}}, "eps": {"quarterly": {}, "annual": {}, "quarterly_forecast": {}, "annual_forecast": {}}}

        merged, log = merge_ticker_data("TEST", existing, incoming, confirm_overwrite=lambda *a: True)

        assert merged["currency"] == "USD"

    def test_flags_currency_mismatch_and_keeps_stored(self):
        existing = empty_store()
        existing["currency"] = "USD"
        incoming = {"currency": "EUR", "revenue": {"quarterly": {}, "annual": {}, "quarterly_forecast": {}, "annual_forecast": {}}, "eps": {"quarterly": {}, "annual": {}, "quarterly_forecast": {}, "annual_forecast": {}}}

        merged, log = merge_ticker_data("TEST", existing, incoming, confirm_overwrite=lambda *a: True)

        assert merged["currency"] == "USD"
        assert any("currency mismatch" in m for m in log)
