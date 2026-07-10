#!/usr/bin/env python3
"""
Build wide-format CSV rows from the earning.yaml data store, for exporting to
Google Sheets.

Each row is one ticker; each period (e.g. "Q1 2025", "2025 Yearly") becomes
its own column, grouped by metric (Revenue/EPS) and period type
(quarterly/annual). Historical and forecast values for the same period share
one column, since a period is only ever in one bucket at a time (see
earnings_data_store's forecast-cleanup rule). The column set is the union of
periods across all requested tickers, so a ticker with fewer historical
quarters just leaves those cells blank.
"""

from typing import Dict, List, Tuple

from earnings_data_store import FORECAST_OF, label_sort_key

STATIC_COLUMNS = [
    "Ticker",
    "Exchange",
    "Company Name",
    "Market Segment",
    "Market Cap (B)",
    "Currency",
]

METRIC_LABELS = {"revenue": "Revenue", "eps": "EPS"}
PERIOD_TYPES = ("quarterly", "annual")
METRICS = ("revenue", "eps")


def _merged_periods(ticker_data: Dict, metric: str, period_type: str) -> Dict[str, float]:
    """Combine historical + forecast points for one metric/period-type into one {period: value} dict."""
    forecast_bucket = FORECAST_OF[period_type]
    merged = dict(ticker_data.get(metric, {}).get(forecast_bucket, {}))
    merged.update(ticker_data.get(metric, {}).get(period_type, {}))
    return merged


def collect_period_columns(
    ticker_data_by_key: Dict[Tuple[str, str], Dict], metric: str, period_type: str
) -> List[str]:
    """Union of period labels across all tickers for one metric/period-type, sorted chronologically."""
    periods = set()
    for ticker_data in ticker_data_by_key.values():
        periods.update(_merged_periods(ticker_data, metric, period_type).keys())
    return sorted(periods, key=label_sort_key)


def build_export_rows(
    ordered_keys: List[Tuple[str, str]], ticker_data_by_key: Dict[Tuple[str, str], Dict]
) -> Tuple[List[str], List[List[str]]]:
    """
    Build the CSV header row and data rows for a wide-format earnings export.

    Args:
        ordered_keys: Ordered list of (exchange, ticker) tuples to include as rows
        ticker_data_by_key: {(exchange, ticker): stored_data}, as returned by
            earnings_data_store.load_existing_data

    Returns:
        (headers, rows) — headers is a list of column names, rows is a list of
        string lists in the same column order
    """
    period_columns = {
        (metric, period_type): collect_period_columns(ticker_data_by_key, metric, period_type)
        for metric in METRICS
        for period_type in PERIOD_TYPES
    }

    headers = list(STATIC_COLUMNS)
    for metric in METRICS:
        for period_type in PERIOD_TYPES:
            for period in period_columns[(metric, period_type)]:
                headers.append(f"{METRIC_LABELS[metric]} {period}")

    rows = []
    for exchange, ticker in ordered_keys:
        data = ticker_data_by_key.get((exchange, ticker), {})
        market_cap = data.get("market_cap_billions")

        row = [
            ticker,
            exchange,
            data.get("company_name") or "",
            data.get("sector") or "",
            f"{market_cap:.2f}" if market_cap is not None else "",
            data.get("currency") or "",
        ]

        for metric in METRICS:
            for period_type in PERIOD_TYPES:
                merged = _merged_periods(data, metric, period_type)
                for period in period_columns[(metric, period_type)]:
                    value = merged.get(period)
                    row.append("" if value is None else str(value))

        rows.append(row)

    return headers, rows
