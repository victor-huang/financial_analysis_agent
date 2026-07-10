#!/usr/bin/env python3
"""
Map a Google Sheet's existing header row onto the earning.yaml data store.

Sheets are free to name and order their earnings columns however they like
(see "ERN DataBase" for the first real example, which even has typos like a
trailing space on "Q1 26 Rev " and inconsistent "act" vs "act." punctuation).
Rather than hardcoding a fixed layout and hoping it matches, this module
PARSES the sheet's live header row into a resolver per column. That means a
sheet's headers can be renamed, reordered, or extended without any code
changes here — only a genuinely new naming convention (e.g. a different way
of denoting "revenue" or "estimate") needs a new regex case below.
"""

import re
from typing import Callable, Dict, List, Optional, Tuple

from earnings_data_store import FORECAST_OF

# Logical field name -> the header text(s) it's known by (normalized: lowercased,
# whitespace-collapsed). Add an alias here whenever a sheet labels one of these
# static profile fields differently.
STATIC_FIELD_ALIASES = {
    "ticker": {"ticker"},
    "exchange": {"exchange"},
    "company_name": {"company name"},
    "sector": {"market segment", "sector"},
    "market_cap_billions": {"market cap (b)", "market cap"},
    "currency": {"currency"},
}

QUARTER_PATTERN = re.compile(
    r"^q(?P<quarter>[1-4])\s+(?P<year>\d{2}|\d{4})\s+(?P<metric>eps|rev)\s*(?P<suffix>est\.?|act\.?)?$"
)
ANNUAL_PATTERN = re.compile(r"^(?P<year>\d{4})\s+(?:est\s+)?(?P<metric>eps|rev)$")


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def _year_to_4digit(year_text: str) -> int:
    year = int(year_text)
    if year < 100:
        return 2000 + year if year < 50 else 1900 + year
    return year


def _static_resolver(field_key: str) -> Callable[[Dict, str, str], str]:
    def resolve(data: Dict, ticker: str, exchange: str) -> str:
        if field_key == "ticker":
            return ticker
        if field_key == "exchange":
            return exchange
        value = data.get(field_key)
        if field_key == "market_cap_billions":
            return f"{value:.2f}" if value is not None else ""
        return value or ""

    return resolve


def _period_resolver(
    metric: str, period_type: str, period_label: str, bucket: str
) -> Callable[[Dict, str, str], str]:
    def resolve(data: Dict, ticker: str, exchange: str) -> str:
        metric_data = data.get(metric, {})
        if bucket == "forecast":
            value = metric_data.get(FORECAST_OF[period_type], {}).get(period_label)
        elif bucket == "historical":
            value = metric_data.get(period_type, {}).get(period_label)
        else:  # "auto": historical takes precedence, falls back to forecast
            value = metric_data.get(period_type, {}).get(period_label)
            if value is None:
                value = metric_data.get(FORECAST_OF[period_type], {}).get(period_label)
        return "" if value is None else str(value)

    return resolve


def parse_header_cell(header_text: str) -> Optional[Callable[[Dict, str, str], str]]:
    """
    Parse one Google Sheet header cell into a resolver function.

    Args:
        header_text: Raw header text as it appears in the sheet

    Returns:
        A resolver(data, ticker, exchange) -> str, or None if the header
        text isn't recognized (that column is left blank on export)
    """
    normalized = _normalize(header_text)

    for field_key, aliases in STATIC_FIELD_ALIASES.items():
        if normalized in aliases:
            return _static_resolver(field_key)

    match = QUARTER_PATTERN.match(normalized)
    if match:
        year = _year_to_4digit(match.group("year"))
        metric = "eps" if match.group("metric") == "eps" else "revenue"
        suffix = (match.group("suffix") or "").rstrip(".")
        bucket = "forecast" if suffix == "est" else "historical" if suffix == "act" else "auto"
        return _period_resolver(metric, "quarterly", f"Q{match.group('quarter')} {year}", bucket)

    match = ANNUAL_PATTERN.match(normalized)
    if match:
        metric = "eps" if match.group("metric") == "eps" else "revenue"
        bucket = "forecast" if " est " in f" {normalized} " else "auto"
        return _period_resolver(metric, "annual", f"{match.group('year')} Yearly", bucket)

    return None


def build_rows_for_headers(
    headers: List[str],
    ordered_keys: List[Tuple[str, str]],
    ticker_data_by_key: Dict[Tuple[str, str], Dict],
) -> Tuple[List[List[str]], List[str]]:
    """
    Build one data row per ticker matching an existing sheet's header row.

    Args:
        headers: The target sheet's existing header row, verbatim
        ordered_keys: Ordered list of (exchange, ticker) tuples to include as rows
        ticker_data_by_key: {(exchange, ticker): stored_data}, as returned by
            earnings_data_store.load_existing_data

    Returns:
        (rows, unrecognized_headers) — rows are string lists in header order;
        unrecognized_headers lists any header text that couldn't be mapped
        (left blank in every row)
    """
    resolvers = []
    unrecognized = []
    for header in headers:
        resolver = parse_header_cell(header)
        resolvers.append(resolver)
        if resolver is None:
            unrecognized.append(header)

    rows = []
    for exchange, ticker in ordered_keys:
        data = ticker_data_by_key.get((exchange, ticker), {})
        rows.append(
            [resolver(data, ticker, exchange) if resolver else "" for resolver in resolvers]
        )

    return rows, unrecognized
