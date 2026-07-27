#!/usr/bin/env python3
"""
Critical path tests for export_earning_store_to_sheets.py row upsert logic.
"""

import sys
import os
from unittest.mock import MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from export_earning_store_to_sheets import (
    _column_letter,
    get_ticker_row_numbers,
    get_next_available_row,
    upsert_rows,
)


class TestColumnLetter:
    """Tests for 1-indexed column number to spreadsheet letter conversion."""

    def test_first_column_is_a(self):
        assert _column_letter(1) == "A"

    def test_twenty_sixth_column_is_z(self):
        assert _column_letter(26) == "Z"

    def test_twenty_seventh_column_is_aa(self):
        assert _column_letter(27) == "AA"

    def test_thirtieth_column_is_ad(self):
        assert _column_letter(30) == "AD"


def _make_client(column_a_values):
    """
    Build a mock client whose values().get() returns column_a_values for any
    range read of column A (both the "from row 2" read used by
    get_ticker_row_numbers and the "whole column" read used by
    get_next_available_row see the same full column contents).
    """
    client = MagicMock()
    client.service.spreadsheets.return_value.values.return_value.get.return_value.execute.return_value = {
        "values": column_a_values
    }
    return client


class TestGetTickerRowNumbers:
    """Tests for mapping existing tickers to their sheet row numbers."""

    def test_maps_tickers_to_row_numbers_starting_at_two(self):
        client = _make_client([["STLD"], ["PAC"]])

        result = get_ticker_row_numbers(client, "sheet-id", "ERN DataBase")

        assert result == {"STLD": 2, "PAC": 3}

    def test_skips_blank_rows(self):
        client = _make_client([["STLD"], [], ["PAC"]])

        result = get_ticker_row_numbers(client, "sheet-id", "ERN DataBase")

        assert result == {"STLD": 2, "PAC": 4}

    def test_uppercases_tickers(self):
        client = _make_client([["stld"]])

        result = get_ticker_row_numbers(client, "sheet-id", "ERN DataBase")

        assert result == {"STLD": 2}


class TestGetNextAvailableRow:
    """Tests for computing the next empty row explicitly (no reliance on the Sheets append heuristic)."""

    def test_next_row_is_after_header_only(self):
        client = _make_client([["    "]])

        assert get_next_available_row(client, "sheet-id", "ERN DataBase") == 2

    def test_next_row_is_after_header_and_existing_tickers(self):
        client = _make_client([["    "], ["STLD"], ["PAC"]])

        assert get_next_available_row(client, "sheet-id", "ERN DataBase") == 4


class TestUpsertRows:
    """Tests for updating existing ticker rows in place vs writing new ones to an explicit row."""

    def test_updates_existing_ticker_in_place(self):
        # get_ticker_row_numbers reads from row 2, so this represents rows 2+
        client = _make_client([["STLD"]])
        headers = ["ticker", "Company name"]
        ordered_keys = [("NASDAQ", "STLD")]
        rows = [["STLD", "Steel Dynamics, Inc."]]

        upsert_rows(client, "sheet-id", "ERN DataBase", headers, ordered_keys, rows)

        batch_mock = client.service.spreadsheets.return_value.values.return_value.batchUpdate
        batch_mock.assert_called_once()
        batch_kwargs = batch_mock.call_args.kwargs
        assert batch_kwargs["body"]["data"] == [
            {"range": "ERN DataBase!A2:B2", "values": [["STLD", "Steel Dynamics, Inc."]]}
        ]

    def test_multiple_existing_tickers_use_a_single_batch_call(self):
        """Regression test: one values().update() call per row hit the Sheets API's
        per-minute write-request quota partway through a run of ~65 tickers, silently
        leaving the rest of the sheet stale. All updates must go through one batch call."""
        client = _make_client([["STLD"], ["PAC"], ["AGNC"]])
        headers = ["ticker", "Company name"]
        ordered_keys = [("NASDAQ", "STLD"), ("NYSE", "PAC"), ("NASDAQ", "AGNC")]
        rows = [["STLD", "Steel Dynamics"], ["PAC", "Grupo Aeroportuario"], ["AGNC", "AGNC Investment"]]

        upsert_rows(client, "sheet-id", "ERN DataBase", headers, ordered_keys, rows)

        batch_mock = client.service.spreadsheets.return_value.values.return_value.batchUpdate
        batch_mock.assert_called_once()
        update_mock = client.service.spreadsheets.return_value.values.return_value.update
        update_mock.assert_not_called()
        assert len(batch_mock.call_args.kwargs["body"]["data"]) == 3

    def test_writes_new_ticker_to_explicit_row_after_header(self):
        # column A read (from get_ticker_row_numbers's row-2 perspective) is empty,
        # meaning no existing tickers; get_next_available_row sees the same mock
        # return value representing just the header row.
        client = _make_client([["    "]])
        headers = ["ticker", "Company name"]
        ordered_keys = [("NASDAQ", "AAPL")]
        rows = [["AAPL", "Apple Inc"]]

        upsert_rows(client, "sheet-id", "ERN DataBase", headers, ordered_keys, rows)

        update_mock = client.service.spreadsheets.return_value.values.return_value.update
        update_mock.assert_called_once()
        update_kwargs = update_mock.call_args.kwargs
        assert update_kwargs["range"] == "ERN DataBase!A2:B2"
        assert update_kwargs["body"] == {"values": [["AAPL", "Apple Inc"]]}

    def test_new_ticker_rows_never_use_append_data_to_sheet(self):
        """Regression test: values().append()'s table-detection heuristic was
        observed to misplace an existing header row, so new rows must be
        written with an explicit range instead."""
        client = _make_client([["    "]])
        headers = ["ticker", "Company name"]
        ordered_keys = [("NASDAQ", "AAPL")]
        rows = [["AAPL", "Apple Inc"]]

        upsert_rows(client, "sheet-id", "ERN DataBase", headers, ordered_keys, rows)

        client.append_data_to_sheet.assert_not_called()
