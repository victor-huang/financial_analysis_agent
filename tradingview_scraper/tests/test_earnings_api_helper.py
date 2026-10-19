#!/usr/bin/env python3
"""
Tests for earnings_api_helper.py's release schedule lookup.
"""

import sys
import os
from datetime import date
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from earnings_api_helper import fetch_release_schedules

OCT_19_2026_1230_UTC = 1792413000


def _scanner_response(data):
    response = MagicMock()
    response.json.return_value = {"data": data}
    return response


class TestFetchReleaseSchedules:
    """Tests for parsing TradingView scanner release schedules."""

    def test_parses_fiscal_period_and_release_dates(self):
        response = _scanner_response(
            [{"s": "NASDAQ:STLD", "d": ["2026-Q2", OCT_19_2026_1230_UTC, OCT_19_2026_1230_UTC]}]
        )

        with patch("earnings_api_helper.requests.post", return_value=response):
            schedules = fetch_release_schedules([("NASDAQ", "STLD")])

        assert schedules == {
            ("NASDAQ", "STLD"): {
                "fiscal_period_current": "2026-Q2",
                "last_release_date": date(2026, 10, 19),
                "next_release_date": date(2026, 10, 19),
            }
        }

    def test_missing_release_dates_are_none(self):
        response = _scanner_response([{"s": "NYSE:WRB", "d": ["2026-Q2", None, None]}])

        with patch("earnings_api_helper.requests.post", return_value=response):
            schedules = fetch_release_schedules([("NYSE", "WRB")])

        assert schedules[("NYSE", "WRB")]["last_release_date"] is None
        assert schedules[("NYSE", "WRB")]["next_release_date"] is None

    def test_requests_all_tickers_in_one_call(self):
        response = _scanner_response([])

        with patch("earnings_api_helper.requests.post", return_value=response) as post_mock:
            fetch_release_schedules([("NASDAQ", "STLD"), ("AMEX", "PRK")])

        post_mock.assert_called_once()
        assert post_mock.call_args.kwargs["json"]["symbols"]["tickers"] == ["NASDAQ:STLD", "AMEX:PRK"]
