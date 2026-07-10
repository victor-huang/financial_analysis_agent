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


class TestGetTickerRowNumbers:
    """Tests for mapping existing tickers to their sheet row numbers."""

    def _make_client(self, values):
        client = MagicMock()
        client.service.spreadsheets.return_value.values.return_value.get.return_value.execute.return_value = {
            "values": values
        }
        return client

    def test_maps_tickers_to_row_numbers_starting_at_two(self):
        client = self._make_client([["STLD"], ["PAC"]])

        result = get_ticker_row_numbers(client, "sheet-id", "ERN DataBase")

        assert result == {"STLD": 2, "PAC": 3}

    def test_skips_blank_rows(self):
        client = self._make_client([["STLD"], [], ["PAC"]])

        result = get_ticker_row_numbers(client, "sheet-id", "ERN DataBase")

        assert result == {"STLD": 2, "PAC": 4}

    def test_uppercases_tickers(self):
        client = self._make_client([["stld"]])

        result = get_ticker_row_numbers(client, "sheet-id", "ERN DataBase")

        assert result == {"STLD": 2}


class TestUpsertRows:
    """Tests for updating existing ticker rows in place vs appending new ones."""

    def _make_client(self, existing_tickers):
        client = MagicMock()
        client.service.spreadsheets.return_value.values.return_value.get.return_value.execute.return_value = {
            "values": [[t] for t in existing_tickers]
        }
        return client

    def test_updates_existing_ticker_in_place_without_appending(self):
        client = self._make_client(["STLD", "PAC"])
        headers = ["ticker", "Company name"]
        ordered_keys = [("NASDAQ", "STLD")]
        rows = [["STLD", "Steel Dynamics, Inc."]]

        upsert_rows(client, "sheet-id", "ERN DataBase", headers, ordered_keys, rows)

        client.service.spreadsheets.return_value.values.return_value.update.assert_called_once()
        update_kwargs = client.service.spreadsheets.return_value.values.return_value.update.call_args.kwargs
        assert update_kwargs["range"] == "ERN DataBase!A2:B2"
        assert update_kwargs["body"] == {"values": [["STLD", "Steel Dynamics, Inc."]]}
        client.append_data_to_sheet.assert_not_called()

    def test_appends_new_ticker_not_already_present(self):
        client = self._make_client(["STLD"])
        headers = ["ticker", "Company name"]
        ordered_keys = [("NASDAQ", "AAPL")]
        rows = [["AAPL", "Apple Inc"]]

        upsert_rows(client, "sheet-id", "ERN DataBase", headers, ordered_keys, rows)

        client.service.spreadsheets.return_value.values.return_value.update.assert_not_called()
        client.append_data_to_sheet.assert_called_once_with(
            spreadsheet_id="sheet-id", data=[["AAPL", "Apple Inc"]], tab_name="ERN DataBase"
        )

    def test_mixed_existing_and_new_tickers_split_correctly(self):
        client = self._make_client(["STLD"])
        headers = ["ticker", "Company name"]
        ordered_keys = [("NASDAQ", "STLD"), ("NASDAQ", "AAPL")]
        rows = [["STLD", "Steel Dynamics, Inc."], ["AAPL", "Apple Inc"]]

        upsert_rows(client, "sheet-id", "ERN DataBase", headers, ordered_keys, rows)

        client.service.spreadsheets.return_value.values.return_value.update.assert_called_once()
        client.append_data_to_sheet.assert_called_once_with(
            spreadsheet_id="sheet-id", data=[["AAPL", "Apple Inc"]], tab_name="ERN DataBase"
        )
