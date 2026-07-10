#!/usr/bin/env python3
"""
Persist scraped Revenue/EPS data to ./company_earnings_data/<exchange>_<ticker>/earning.yaml
and merge newly scraped data into it on subsequent runs instead of overwriting.

Merge rules:
- Reported (actual) data points are additive by default. If a period already has a
  reported value and a new scrape returns a *different* value for that same period,
  this is a discrepancy: the user is prompted to confirm before overwriting.
- Forecast data points are overwritten automatically on every run (since estimates
  change over time), but each overwrite is logged for visibility.
- When a period that used to be a forecast now has reported data, the stale forecast
  entry for that period is dropped.
"""

import re
from pathlib import Path
from typing import Dict, List, Tuple

import yaml

DATA_ROOT = Path("company_earnings_data")

REPORTED_BUCKETS = ("quarterly", "annual")
FORECAST_BUCKETS = ("quarterly_forecast", "annual_forecast")
FORECAST_OF = {"quarterly": "quarterly_forecast", "annual": "annual_forecast"}

# Static profile fields rarely change once scraped; a mismatch on rerun is
# treated like a data-quality flag rather than an expected update.
STATIC_PROFILE_FIELDS = ("currency", "company_name", "sector")
# Snapshot fields are inherently time-varying (e.g. market cap moves daily),
# so they're refreshed automatically every run, just like forecast data.
SNAPSHOT_FIELDS = ("market_cap_billions",)


def _label_sort_key(label: str) -> Tuple[int, int]:
    """Sort key for display labels like 'Q1 2025' or '2025 Yearly'."""
    quarterly_match = re.match(r"^Q(\d) (\d{4})$", label)
    if quarterly_match:
        return (int(quarterly_match.group(2)), int(quarterly_match.group(1)))

    annual_match = re.match(r"^(\d{4}) Yearly$", label)
    if annual_match:
        return (int(annual_match.group(1)), 0)

    return (9999, 0)


def get_ticker_dir(exchange: str, ticker: str) -> Path:
    return DATA_ROOT / f"{exchange.upper()}_{ticker.upper()}"


def get_yaml_path(exchange: str, ticker: str) -> Path:
    return get_ticker_dir(exchange, ticker) / "earning.yaml"


def load_existing_data(exchange: str, ticker: str) -> Dict:
    """Load previously saved data for a ticker, or an empty structure if none exists."""
    path = get_yaml_path(exchange, ticker)
    if not path.exists():
        return {
            **{field: None for field in STATIC_PROFILE_FIELDS + SNAPSHOT_FIELDS},
            "revenue": {},
            "eps": {},
        }

    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    for field in STATIC_PROFILE_FIELDS + SNAPSHOT_FIELDS:
        data.setdefault(field, None)
    data.setdefault("revenue", {})
    data.setdefault("eps", {})
    for metric in ("revenue", "eps"):
        for bucket in REPORTED_BUCKETS + FORECAST_BUCKETS:
            data[metric].setdefault(bucket, {})

    return data


def save_data(exchange: str, ticker: str, data: Dict) -> Path:
    """Sort each bucket chronologically and write the merged data to disk."""
    sorted_data = {field: data.get(field) for field in STATIC_PROFILE_FIELDS + SNAPSHOT_FIELDS}
    for metric in ("revenue", "eps"):
        sorted_data[metric] = {}
        for bucket in REPORTED_BUCKETS + FORECAST_BUCKETS:
            points = data.get(metric, {}).get(bucket, {})
            sorted_data[metric][bucket] = {
                label: points[label] for label in sorted(points, key=_label_sort_key)
            }

    ticker_dir = get_ticker_dir(exchange, ticker)
    ticker_dir.mkdir(parents=True, exist_ok=True)
    path = get_yaml_path(exchange, ticker)

    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(sorted_data, f, sort_keys=False, allow_unicode=True)

    return path


def _values_differ(old_value, new_value) -> bool:
    if old_value is None or new_value is None:
        return False
    if isinstance(old_value, float) or isinstance(new_value, float):
        return abs(float(old_value) - float(new_value)) > 1e-6
    return old_value != new_value


def _merge_reported_bucket(
    ticker: str,
    metric: str,
    bucket: str,
    existing: Dict[str, float],
    incoming: Dict[str, float],
    confirm_overwrite,
) -> Tuple[Dict[str, float], List[str]]:
    """Merge one reported (historical) bucket, flagging discrepancies for confirmation."""
    merged = dict(existing)
    log = []

    for period, new_value in incoming.items():
        old_value = merged.get(period)

        if period not in merged:
            merged[period] = new_value
            log.append(f"{ticker}: added new {metric} {bucket} data point {period} = {new_value}")
        elif _values_differ(old_value, new_value):
            should_overwrite = confirm_overwrite(
                ticker, metric, bucket, period, old_value, new_value
            )
            if should_overwrite:
                merged[period] = new_value
                log.append(
                    f"{ticker}: OVERWROTE {metric} {bucket} {period}: "
                    f"{old_value} -> {new_value} (user confirmed)"
                )
            else:
                log.append(
                    f"{ticker}: KEPT existing {metric} {bucket} {period} = {old_value} "
                    f"(user declined overwrite to {new_value})"
                )

    return merged, log


def _merge_forecast_bucket(
    ticker: str,
    metric: str,
    bucket: str,
    existing: Dict[str, float],
    incoming: Dict[str, float],
) -> Tuple[Dict[str, float], List[str]]:
    """Merge one forecast bucket, always overwriting but logging every change."""
    merged = dict(existing)
    log = []

    for period, new_value in incoming.items():
        old_value = merged.get(period)

        if period not in merged:
            log.append(f"{ticker}: added new {metric} {bucket} forecast {period} = {new_value}")
        elif _values_differ(old_value, new_value):
            log.append(
                f"{ticker}: forecast updated for {metric} {bucket} {period}: "
                f"{old_value} -> {new_value} (auto-overwritten)"
            )

        merged[period] = new_value

    return merged, log


def merge_ticker_data(
    ticker: str, existing: Dict, incoming: Dict, confirm_overwrite
) -> Tuple[Dict, List[str]]:
    """
    Merge freshly scraped data into previously stored data.

    Args:
        ticker: Ticker symbol (for log messages)
        existing: Data loaded via load_existing_data
        incoming: Freshly transformed scrape data (see quarterly_annual_collector.transform_financial_data)
        confirm_overwrite: Callable(ticker, metric, bucket, period, old_value, new_value) -> bool,
            used to ask the user whether to overwrite a conflicting reported data point

    Returns:
        (merged_data, log_messages)
    """
    merged = {field: existing.get(field) for field in STATIC_PROFILE_FIELDS}
    merged["revenue"] = {}
    merged["eps"] = {}
    log = []

    for field in STATIC_PROFILE_FIELDS:
        new_value = incoming.get(field)
        old_value = existing.get(field)
        if new_value and old_value and new_value != old_value:
            log.append(
                f"{ticker}: {field} mismatch — stored {old_value!r}, scraped {new_value!r}. "
                f"Keeping stored value; verify manually."
            )
        elif new_value and not old_value:
            merged[field] = new_value
            log.append(f"{ticker}: recorded {field} = {new_value!r}")

    for field in SNAPSHOT_FIELDS:
        new_value = incoming.get(field)
        old_value = existing.get(field)
        merged[field] = new_value if new_value is not None else old_value
        if new_value is not None and old_value is not None and _values_differ(old_value, new_value):
            log.append(f"{ticker}: {field} updated: {old_value} -> {new_value} (auto-refreshed)")
        elif new_value is not None and old_value is None:
            log.append(f"{ticker}: recorded {field} = {new_value}")

    for metric in ("revenue", "eps"):
        merged[metric] = {}

        for bucket in REPORTED_BUCKETS:
            bucket_merged, bucket_log = _merge_reported_bucket(
                ticker,
                metric,
                bucket,
                existing.get(metric, {}).get(bucket, {}),
                incoming.get(metric, {}).get(bucket, {}),
                confirm_overwrite,
            )
            merged[metric][bucket] = bucket_merged
            log.extend(bucket_log)

        for bucket in FORECAST_BUCKETS:
            bucket_merged, bucket_log = _merge_forecast_bucket(
                ticker,
                metric,
                bucket,
                existing.get(metric, {}).get(bucket, {}),
                incoming.get(metric, {}).get(bucket, {}),
            )
            merged[metric][bucket] = bucket_merged
            log.extend(bucket_log)

        # A period that now has reported data is no longer a forecast — drop it
        # from the forecast bucket so the two don't disagree.
        for reported_bucket, forecast_bucket in FORECAST_OF.items():
            reported_periods = merged[metric][reported_bucket]
            forecast_bucket_data = merged[metric][forecast_bucket]
            for period in list(forecast_bucket_data):
                if period in reported_periods:
                    del forecast_bucket_data[period]
                    log.append(
                        f"{ticker}: removed stale {metric} {forecast_bucket} forecast for "
                        f"{period} (now reported)"
                    )

    return merged, log


def prompt_confirm_overwrite(
    ticker: str, metric: str, bucket: str, period: str, old_value, new_value
) -> bool:
    """Default confirm_overwrite implementation: ask interactively on the CLI."""
    print(
        f"\n⚠ Discrepancy for {ticker} {metric} {bucket} {period}: "
        f"stored={old_value}, scraped={new_value}"
    )
    answer = input("  Overwrite stored value with scraped value? [y/N]: ").strip().lower()
    return answer in ("y", "yes")
