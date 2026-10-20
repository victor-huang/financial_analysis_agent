#!/usr/bin/env python3
"""
Critical path tests for sheet_column_mapping.py header parsing.
"""

import sys
import os
from datetime import date
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from sheet_column_mapping import parse_header_cell, build_rows_for_headers

# The original "ERN DataBase" header, captured verbatim (including its typos:
# a trailing space on "Q1 26 Rev " and inconsistent "act" vs "act." punctuation).
# Only the single "current" quarter/year had a separate Est./actual split.
ERN_DATABASE_HEADER_V1 = [
    "ticker", "Company name", "Market segment", "Market Cap (B)",
    "Q2 24 EPS", "Q2 24 Rev", "Q3 24 EPS", "Q3 24 Rev", "Q4 24 EPS", "Q4 24 Rev",
    "2024 EPS", "2024 Rev",
    "Q1 25 EPS", "Q1 25 Rev", "Q2 25 EPS", "Q2 25 Rev", "Q3 25 EPS", "Q3 25 Rev", "Q4 25 EPS", "Q4 25 Rev",
    "2025 EPS", "2025 Rev",
    "Q1 26 EPS", "Q1 26 Rev ",
    "Q2 26 EPS Est.", "Q2 26 EPS act", "Q2 26 Rev Est.", "Q2 26 Rev act.",
    "2026 Est EPS", "2026 Est Rev",
]

# The current "ERN DataBase" header after the user added columns: every
# quarter/year now has both an "Est." column and a plain (actual) column,
# and the ticker column's header cell is blank instead of literal "ticker".
ERN_DATABASE_HEADER_V2 = [
    "    ", "Company name", "Market segment", "Market Cap (B)",
    "Q3 24 EPS Est.", "Q3 24 EPS", "Q3 24 Rev Est.", "Q3 24 Rev",
    "Q4 24 EPS Est.", "Q4 24 EPS", "Q4 24 Rev Est.", "Q4 24 Rev",
    "2024 EPS Est.", "2024 EPS", "2024 Rev Est.", "2024 Rev",
    "Q1 25 EPS Est.", "Q1 25 EPS", "Q1 25 Rev Est.", "Q1 25 Rev",
    "Q2 25 EPS Est.", "Q2 25 EPS", "Q2 25 Rev Est.", "Q2 25 Rev",
    "Q3 25 EPS Est.", "Q3 25 EPS", "Q3 25 Rev Est.", "Q3 25 Rev",
    "Q4 25 EPS Est.", "Q4 25 EPS", "Q4 25 Rev Est.", "Q4 25 Rev",
    "2025 EPS Est.", "2025 EPS", "2025 Rev Est.", "2025 Rev",
    "Q1 26 EPS Est.", "Q1 26 EPS", "Q1 26 Rev Est.", "Q1 26 Rev ",
    "Q2 26 EPS Est.", "Q2 26 EPS", "Q2 26 Rev Est.", "Q2 26 Rev",
    "Q3 26 EPS Est.", "Q3 26 EPS", "Q3 26 Rev Est.", "Q3 26 Rev",
    "Q4 26 EPS Est.", "Q4 26 EPS", "Q4 26 Rev Est.", "Q4 26 Rev",
    "2026 EPS Est.", "2026 EPS Act", "2026 Rev Est.", "2026 Rev Act",
]

# The current live header: the user dropped the "Act" suffix in favor of the
# plain name for actual/reported values everywhere, including the final
# annual columns ("2026 EPS " / "2026 Rev" instead of "2026 EPS Act").
ERN_DATABASE_HEADER_V3 = ERN_DATABASE_HEADER_V2[:-4] + [
    "2026 EPS Est.", "2026 EPS ", "2026 Rev Est.", "2026 Rev",
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


def _schedule(fiscal_period_current, last_release_date, next_release_date, fiscal_period_end_date=None):
    return {
        "release_schedule": {
            "fiscal_period_current": fiscal_period_current,
            "fiscal_period_end_date": fiscal_period_end_date,
            "last_release_date": last_release_date,
            "next_release_date": next_release_date,
        }
    }


class TestParseEarningsSeasonQuarterFromSchedule:
    """Tests for the "Quarter" column: the fiscal quarter of the release nearest today."""

    @patch("sheet_column_mapping._today", return_value=date(2026, 10, 19))
    def test_release_day_before_reporting_is_the_quarter_about_to_release(self, _):
        resolver = parse_header_cell("Quarter")
        data = _schedule("2026-Q2", date(2026, 7, 20), date(2026, 10, 19))
        assert resolver(data, "STLD", "NASDAQ") == "Q3"

    @patch("sheet_column_mapping._today", return_value=date(2026, 10, 19))
    def test_release_day_after_reporting_is_the_quarter_just_released(self, _):
        resolver = parse_header_cell("Quarter")
        data = _schedule("2026-Q3", date(2026, 10, 19), date(2027, 1, 20))
        assert resolver(data, "STLD", "NASDAQ") == "Q3"

    @patch("sheet_column_mapping._today", return_value=date(2026, 11, 15))
    def test_stays_on_just_released_quarter_while_last_release_is_nearer(self, _):
        resolver = parse_header_cell("Quarter")
        data = _schedule("2026-Q3", date(2026, 10, 19), date(2027, 1, 20))
        assert resolver(data, "STLD", "NASDAQ") == "Q3"

    @patch("sheet_column_mapping._today", return_value=date(2027, 1, 1))
    def test_moves_to_next_quarter_once_next_release_is_nearer(self, _):
        resolver = parse_header_cell("Quarter")
        data = _schedule("2026-Q3", date(2026, 10, 19), date(2027, 1, 20))
        assert resolver(data, "STLD", "NASDAQ") == "Q4"

    @patch("sheet_column_mapping._today", return_value=date(2027, 1, 20))
    def test_wraps_from_fiscal_q4_to_q1(self, _):
        resolver = parse_header_cell("Quarter")
        data = _schedule("2026-Q4", date(2026, 10, 19), date(2027, 1, 20))
        assert resolver(data, "STLD", "NASDAQ") == "Q1"

    @patch("sheet_column_mapping._today", return_value=date(2026, 10, 19))
    def test_no_next_release_date_uses_latest_reported_quarter(self, _):
        resolver = parse_header_cell("Quarter")
        data = _schedule("2026-Q3", date(2026, 10, 19), None)
        assert resolver(data, "STLD", "NASDAQ") == "Q3"

    @patch("sheet_column_mapping._today", return_value=date(2026, 10, 19))
    def test_no_last_release_date_uses_quarter_after_latest_reported(self, _):
        resolver = parse_header_cell("Quarter")
        data = _schedule("2026-Q2", None, date(2026, 10, 19))
        assert resolver(data, "NEWCO", "NYSE") == "Q3"

    @patch("sheet_column_mapping._today", return_value=date(2026, 12, 4))
    def test_equally_distant_releases_use_the_just_released_quarter(self, _):
        resolver = parse_header_cell("Quarter")
        data = _schedule("2026-Q3", date(2026, 10, 19), date(2027, 1, 19))
        assert resolver(data, "STLD", "NASDAQ") == "Q3"

    @patch("sheet_column_mapping._today", return_value=date(2026, 10, 19))
    def test_schedule_takes_precedence_over_stored_quarters(self, _):
        resolver = parse_header_cell("Quarter")
        data = {
            **_schedule("2026-Q3", date(2026, 10, 19), date(2027, 1, 20)),
            "eps": {"quarterly": {"Q3 2026": 5.4}},
        }
        assert resolver(data, "STLD", "NASDAQ") == "Q3"


class TestParseEarningsSeasonQuarterFromPeriodEnd:
    """Tests for the "Quarter" column when the schedule includes the latest quarter's period end date."""

    @patch("sheet_column_mapping._today", return_value=date(2026, 10, 19))
    def test_release_day_before_reporting_is_the_quarter_about_to_release(self, _):
        resolver = parse_header_cell("Quarter")
        data = _schedule("2026-Q2", date(2026, 7, 20), date(2026, 10, 19), date(2026, 6, 30))
        assert resolver(data, "STLD", "NASDAQ") == "Q3"

    @patch("sheet_column_mapping._today", return_value=date(2026, 10, 19))
    def test_release_day_while_scanner_still_shows_previous_quarter(self, _):
        """Regression test: on release day TradingView moved last_release_date to
        today while fiscal_period_current still said Q2, which yielded "Q2"."""
        resolver = parse_header_cell("Quarter")
        data = _schedule("2026-Q2", date(2026, 10, 19), date(2027, 1, 27), date(2026, 6, 30))
        assert resolver(data, "STLD", "NASDAQ") == "Q3"

    @patch("sheet_column_mapping._today", return_value=date(2026, 10, 19))
    def test_release_day_after_scanner_updates_to_released_quarter(self, _):
        resolver = parse_header_cell("Quarter")
        data = _schedule("2026-Q3", date(2026, 10, 19), date(2027, 1, 27), date(2026, 9, 30))
        assert resolver(data, "STLD", "NASDAQ") == "Q3"

    @patch("sheet_column_mapping._today", return_value=date(2027, 1, 10))
    def test_moves_to_next_quarter_once_next_release_is_nearer(self, _):
        resolver = parse_header_cell("Quarter")
        data = _schedule("2026-Q3", date(2026, 10, 19), date(2027, 1, 27), date(2026, 9, 30))
        assert resolver(data, "STLD", "NASDAQ") == "Q4"

    @patch("sheet_column_mapping._today", return_value=date(2026, 10, 19))
    def test_non_calendar_fiscal_year(self, _):
        resolver = parse_header_cell("Quarter")
        data = _schedule("2026-Q1", date(2026, 10, 19), date(2027, 1, 14), date(2026, 5, 31))
        assert resolver(data, "KARO", "NASDAQ") == "Q2"

    @patch("sheet_column_mapping._today", return_value=date(2027, 1, 27))
    def test_wraps_from_fiscal_q4_to_q1(self, _):
        resolver = parse_header_cell("Quarter")
        data = _schedule("2026-Q4", date(2027, 1, 27), date(2027, 4, 20), date(2026, 9, 30))
        assert resolver(data, "STLD", "NASDAQ") == "Q1"

    @patch("sheet_column_mapping._today", return_value=date(2026, 10, 22))
    def test_52_53_week_fiscal_quarter_end(self, _):
        resolver = parse_header_cell("Quarter")
        data = _schedule("2026-Q2", date(2026, 7, 23), date(2026, 10, 22), date(2026, 6, 27))
        assert resolver(data, "NEWCO", "NYSE") == "Q3"


class TestParseEarningsSeasonQuarterFallback:
    """Tests for the "Quarter" column when no usable release schedule is available."""

    def test_returns_quarter_after_latest_reported(self):
        resolver = parse_header_cell("Quarter")
        data = {"eps": {"quarterly": {"Q1 2026": 1.1, "Q2 2026": 1.2}}}
        assert resolver(data, "STLD", "NASDAQ") == "Q3"

    def test_schedule_without_fiscal_period_falls_back_to_store(self):
        resolver = parse_header_cell("Quarter")
        data = {**_schedule(None, date(2026, 7, 20), date(2026, 10, 19)), "eps": {"quarterly": {"Q2 2026": 1.2}}}
        assert resolver(data, "STLD", "NASDAQ") == "Q3"

    def test_wraps_from_fiscal_q4_to_q1(self):
        resolver = parse_header_cell("Quarter")
        data = {"eps": {"quarterly": {"Q3 2026": 1.1, "Q4 2026": 1.2}}}
        assert resolver(data, "NVDA", "NASDAQ") == "Q1"

    def test_uses_revenue_when_it_is_reported_later_than_eps(self):
        resolver = parse_header_cell("Quarter")
        data = {"eps": {"quarterly": {"Q2 2026": 1.2}}, "revenue": {"quarterly": {"Q3 2026": 4300.0}}}
        assert resolver(data, "STLD", "NASDAQ") == "Q4"

    def test_falls_back_to_earliest_forecast_when_nothing_reported(self):
        resolver = parse_header_cell("Quarter")
        data = {"eps": {"quarterly": {}, "quarterly_forecast": {"Q4 2026": 0.3, "Q3 2026": 0.2}}}
        assert resolver(data, "NEWCO", "NYSE") == "Q3"

    def test_ignores_unparseable_reported_labels(self):
        """Regression test: an unparseable label sorted as the latest quarter and yielded "Q1"."""
        resolver = parse_header_cell("Quarter")
        data = {"eps": {"quarterly": {"Q2 2026": 1.2, "Q3 '26": 1.3}}}
        assert resolver(data, "STLD", "NASDAQ") == "Q3"

    def test_unusable_schedule_logs_a_warning(self, caplog):
        resolver = parse_header_cell("Quarter")
        data = {**_schedule("2026-FY", date(2026, 7, 20), date(2026, 10, 19)), "eps": {"quarterly": {"Q2 2026": 1.2}}}

        with caplog.at_level("WARNING", logger="sheet_column_mapping"):
            resolver(data, "STLD", "NASDAQ")

        assert "NASDAQ:STLD: unusable release schedule" in caplog.text

    def test_missing_schedule_does_not_log_a_warning(self, caplog):
        resolver = parse_header_cell("Quarter")

        with caplog.at_level("WARNING", logger="sheet_column_mapping"):
            resolver({"eps": {"quarterly": {"Q2 2026": 1.2}}}, "STLD", "NASDAQ")

        assert caplog.text == ""

    def test_no_quarterly_data_leaves_cell_untouched(self):
        resolver = parse_header_cell("Quarter")
        assert resolver({"eps": {"quarterly": {}, "quarterly_forecast": {}}}, "STLD", "NASDAQ") is None


class TestTickerColumnAlwaysColumnA:
    """Column A is always the ticker column regardless of its header text."""

    def test_blank_header_still_resolves_to_ticker(self):
        rows, unrecognized = build_rows_for_headers(["    "], [("NASDAQ", "STLD")], {})
        assert rows == [["STLD"]]
        assert unrecognized == []

    def test_literal_ticker_header_still_works(self):
        rows, unrecognized = build_rows_for_headers(["ticker"], [("NASDAQ", "STLD")], {})
        assert rows == [["STLD"]]
        assert unrecognized == []


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

    def test_plain_column_stays_blank_for_forecast_only_quarter(self):
        """A future quarter's plain (no-suffix) column must not leak the forecast value
        into what's meant to be the actual/reported column — that's what the paired
        Est. column is for."""
        resolver = parse_header_cell("Q3 26 EPS")
        data = {"eps": {"quarterly": {}, "quarterly_forecast": {"Q3 2026": 5.08}}}
        assert resolver(data, "STLD", "NASDAQ") == ""

    def test_est_column_reads_forecast_even_when_plain_column_exists(self):
        resolver = parse_header_cell("Q3 26 EPS Est.")
        data = {"eps": {"quarterly": {}, "quarterly_forecast": {"Q3 2026": 5.08}}}
        assert resolver(data, "STLD", "NASDAQ") == "5.08"


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

    def test_est_suffixed_year_resolves_from_forecast(self):
        """Newer convention: suffix after the metric ('2026 EPS Est.') instead of
        prefixed before it ('2026 Est EPS')."""
        resolver = parse_header_cell("2026 EPS Est.")
        data = {"eps": {"annual": {}, "annual_forecast": {"2026 Yearly": 16.44}}}
        assert resolver(data, "STLD", "NASDAQ") == "16.44"

    def test_act_suffixed_year_resolves_from_historical(self):
        resolver = parse_header_cell("2026 EPS Act")
        data = {"eps": {"annual": {"2026 Yearly": 17.0}, "annual_forecast": {"2026 Yearly": 16.44}}}
        assert resolver(data, "STLD", "NASDAQ") == "17.0"

    def test_act_suffixed_year_blank_when_not_yet_reported(self):
        resolver = parse_header_cell("2026 Rev Act")
        data = {"revenue": {"annual": {}, "annual_forecast": {"2026 Yearly": 22600.0}}}
        assert resolver(data, "STLD", "NASDAQ") == ""

    def test_plain_annual_column_stays_blank_for_forecast_only_year(self):
        resolver = parse_header_cell("2026 EPS")
        data = {"eps": {"annual": {}, "annual_forecast": {"2026 Yearly": 16.44}}}
        assert resolver(data, "STLD", "NASDAQ") == ""


class TestBuildRowsForHeaders:
    """Tests for the full row-building pass against the real ERN DataBase header."""

    def test_every_v1_header_column_maps(self):
        _, unrecognized = build_rows_for_headers(ERN_DATABASE_HEADER_V1, [], {})
        assert unrecognized == []

    def test_every_v2_header_column_maps(self):
        _, unrecognized = build_rows_for_headers(ERN_DATABASE_HEADER_V2, [], {})
        assert unrecognized == []

    def test_every_v3_header_column_maps(self):
        _, unrecognized = build_rows_for_headers(ERN_DATABASE_HEADER_V3, [], {})
        assert unrecognized == []

    def test_v3_plain_annual_column_is_blank_when_not_reported(self):
        data = {
            ("NASDAQ", "STLD"): {
                "eps": {"quarterly": {}, "quarterly_forecast": {}, "annual": {}, "annual_forecast": {"2026 Yearly": 16.44}},
                "revenue": {"quarterly": {}, "quarterly_forecast": {}, "annual": {}, "annual_forecast": {}},
            }
        }

        rows, _ = build_rows_for_headers(
            ["    ", "2026 EPS Est.", "2026 EPS "], [("NASDAQ", "STLD")], data
        )

        assert rows == [["STLD", "16.44", ""]]

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

    def test_unrecognized_column_is_none_so_sheets_skips_the_cell(self):
        """Regression test: writing "" to an unrecognized column (e.g. a manual
        Note column) cleared it on every in-place row update; the Sheets API
        only leaves a cell untouched when its value is null."""
        rows, unrecognized = build_rows_for_headers(["ticker", "Note"], [("NASDAQ", "STLD")], {})

        assert rows == [["STLD", None]]
        assert unrecognized == ["Note"]

