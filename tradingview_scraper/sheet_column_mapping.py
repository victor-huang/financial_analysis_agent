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

import logging
import re
from datetime import date
from typing import Callable, Dict, List, Optional, Tuple

from earnings_data_store import FORECAST_OF, label_sort_key

logger = logging.getLogger(__name__)

EARNINGS_SEASON_QUARTER_ALIASES = {"quarter"}
STORE_QUARTER_LABEL_PATTERN = re.compile(r"^Q[1-4] \d{4}$")

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
# Supports both the "2026 Est EPS" (estimate before the metric) and
# "2026 EPS Est." / "2026 EPS Act" (suffix after the metric) conventions,
# since the same sheet has used both over time.
ANNUAL_PATTERN = re.compile(
    r"^(?P<year>\d{4})\s+(?P<prefix_est>est\s+)?(?P<metric>eps|rev)\s*(?P<suffix>est\.?|act\.?)?$"
)


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
        else:  # "historical": blank until actually reported, even if a forecast exists
            value = metric_data.get(period_type, {}).get(period_label)
        return "" if value is None else str(value)

    return resolve


def _today() -> date:
    return date.today()


def _quarter_from_release_schedule(schedule: Dict) -> Optional[str]:
    """
    The fiscal quarter of whichever release is nearer today, the last or the
    next one. This keeps the quarter stable across release day, whether or not
    the company has reported yet: before the release it's the quarter after
    fiscal_period_current, and once reported fiscal_period_current itself
    becomes that quarter while the last release is 0 days away.
    """
    fiscal_period = schedule.get("fiscal_period_current")
    match = re.match(r"^\d{4}-Q(?P<quarter>[1-4])$", fiscal_period or "")
    last_release = schedule.get("last_release_date")
    next_release = schedule.get("next_release_date")
    if not match or not (last_release or next_release):
        return None

    latest_quarter = int(match.group("quarter"))
    today = _today()
    if next_release is None:
        return f"Q{latest_quarter}"
    if last_release is None:
        return f"Q{latest_quarter % 4 + 1}"
    if (today - last_release).days <= (next_release - today).days:
        return f"Q{latest_quarter}"
    return f"Q{latest_quarter % 4 + 1}"


def _earnings_season_quarter(data: Dict, ticker: str, exchange: str) -> Optional[str]:
    """
    The fiscal quarter of the earnings release nearest today (e.g. "Q3"), from
    the release schedule attached as data["release_schedule"] (see
    earnings_api_helper.fetch_release_schedules).

    Without a usable schedule, falls back to the store: the quarter after the
    latest reported one in either metric, or the earliest forecast quarter if
    nothing has been reported yet. Store labels are already fiscal quarters,
    not calendar ones. Returns None when there's no quarterly data at all so
    the sheet's existing cell is left untouched rather than cleared.
    """
    schedule = data.get("release_schedule")
    scheduled_quarter = _quarter_from_release_schedule(schedule or {})
    if scheduled_quarter:
        return scheduled_quarter
    if schedule:
        logger.warning(
            f"{exchange}:{ticker}: unusable release schedule {schedule}, "
            f"Quarter column will use stored data"
        )

    reported_labels = [
        label
        for metric in ("eps", "revenue")
        for label in data.get(metric, {}).get("quarterly", {})
        if STORE_QUARTER_LABEL_PATTERN.match(label)
    ]
    if reported_labels:
        _, latest_quarter = label_sort_key(max(reported_labels, key=label_sort_key))
        return f"Q{latest_quarter % 4 + 1}"

    forecast_labels = [
        label
        for metric in ("eps", "revenue")
        for label in data.get(metric, {}).get("quarterly_forecast", {})
        if STORE_QUARTER_LABEL_PATTERN.match(label)
    ]
    if forecast_labels:
        return min(forecast_labels, key=label_sort_key).split(" ")[0]
    return None


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

    if normalized in EARNINGS_SEASON_QUARTER_ALIASES:
        return _earnings_season_quarter

    match = QUARTER_PATTERN.match(normalized)
    if match:
        year = _year_to_4digit(match.group("year"))
        metric = "eps" if match.group("metric") == "eps" else "revenue"
        suffix = (match.group("suffix") or "").rstrip(".")
        bucket = "forecast" if suffix == "est" else "historical"
        return _period_resolver(metric, "quarterly", f"Q{match.group('quarter')} {year}", bucket)

    match = ANNUAL_PATTERN.match(normalized)
    if match:
        metric = "eps" if match.group("metric") == "eps" else "revenue"
        suffix = (match.group("suffix") or "").rstrip(".")
        is_estimate = bool(match.group("prefix_est")) or suffix == "est"
        bucket = "forecast" if is_estimate else "historical"
        return _period_resolver(metric, "annual", f"{match.group('year')} Yearly", bucket)

    return None


def build_rows_for_headers(
    headers: List[str],
    ordered_keys: List[Tuple[str, str]],
    ticker_data_by_key: Dict[Tuple[str, str], Dict],
) -> Tuple[List[List[Optional[str]]], List[str]]:
    """
    Build one data row per ticker matching an existing sheet's header row.

    Args:
        headers: The target sheet's existing header row, verbatim
        ordered_keys: Ordered list of (exchange, ticker) tuples to include as rows
        ticker_data_by_key: {(exchange, ticker): stored_data}, as returned by
            earnings_data_store.load_existing_data

    Returns:
        (rows, unrecognized_headers) — rows are lists in header order, with
        None in every unrecognized column; unrecognized_headers lists any
        header text that couldn't be mapped

    Unrecognized columns are None rather than "" because the Sheets API skips
    null values but clears a cell written with "" — so manually maintained
    columns (notes, flags) survive an in-place row update.
    """
    resolvers = []
    unrecognized = []
    for i, header in enumerate(headers):
        # Column A is always the ticker column by convention (it's also
        # hardcoded as such in earnings_data_store row lookups), regardless
        # of what its header cell says — sheets have been seen leaving it
        # blank or unlabeled entirely.
        if i == 0:
            resolvers.append(_static_resolver("ticker"))
            continue

        resolver = parse_header_cell(header)
        resolvers.append(resolver)
        if resolver is None:
            unrecognized.append(header)

    rows = []
    for exchange, ticker in ordered_keys:
        data = ticker_data_by_key.get((exchange, ticker), {})
        rows.append(
            [resolver(data, ticker, exchange) if resolver else None for resolver in resolvers]
        )

    return rows, unrecognized
