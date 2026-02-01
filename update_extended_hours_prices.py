#!/usr/bin/env python3
"""
Script to fetch extended hours stock prices and update a Google Spreadsheet.

Supports pre-market and post-market (after-hours) prices.
"""

import argparse
import json
import logging
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

import yfinance as yf

_shutdown_requested = False

from financial_analysis_agent.config import get_config
from financial_analysis_agent.export import GoogleSheetsClient

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def signal_handler(signum, frame):
    """Handle shutdown signals gracefully."""
    global _shutdown_requested
    sig_name = signal.Signals(signum).name
    logger.info(f"Received {sig_name}, shutting down gracefully...")
    _shutdown_requested = True


def create_sheets_client() -> GoogleSheetsClient:
    """Create and return a GoogleSheetsClient using credentials from config."""
    config = get_config()

    credentials_path = config.get("apis.google_sheets.credentials_path")
    credentials_json_str = config.get("apis.google_sheets.credentials_json")

    if credentials_path and Path(credentials_path).exists():
        logger.info(f"Using credentials from file: {credentials_path}")
        return GoogleSheetsClient(credentials_path=credentials_path)
    elif credentials_json_str:
        logger.info("Using credentials from environment variable")
        credentials_json = json.loads(credentials_json_str)
        return GoogleSheetsClient(service_account_info=credentials_json)
    else:
        raise ValueError(
            "Google Sheets credentials not configured. "
            "Please set GOOGLE_SHEETS_CREDENTIALS_PATH or "
            "GOOGLE_SHEETS_CREDENTIALS_JSON in your .env file"
        )


def get_extended_hours_price(
    ticker: str, price_type: str = "post"
) -> Tuple[
    Optional[float], Optional[float], Optional[str], Optional[float], Optional[float]
]:
    """
    Fetch extended hours price and regular close price for a ticker.

    Args:
        ticker: Stock ticker symbol
        price_type: 'pre' for pre-market, 'post' for after-hours, 'both' for both

    Returns:
        Tuple of (extended_price, change_percent, market_state, close_price, previous_close)
    """
    try:
        stock = yf.Ticker(ticker)
        info = stock.info

        market_state = info.get("marketState", "UNKNOWN")
        close_price = info.get("regularMarketPrice")
        previous_close = info.get("previousClose")

        if price_type == "pre":
            price = info.get("preMarketPrice")
            change = info.get("preMarketChangePercent")
            if change is not None:
                change = round(change * 100, 2)
        elif price_type == "post":
            price = info.get("postMarketPrice")
            change = info.get("postMarketChangePercent")
            if change is not None:
                change = round(change * 100, 2)
        else:
            price = info.get("postMarketPrice") or info.get("preMarketPrice")
            change = info.get("postMarketChangePercent") or info.get(
                "preMarketChangePercent"
            )
            if change is not None:
                change = round(change * 100, 2)

        if price is None:
            price = info.get("regularMarketPrice")
            change = info.get("regularMarketChangePercent")
            if change is not None:
                change = round(change, 2)
            logger.warning(
                f"{ticker}: Extended hours price not available, using regular market price"
            )

        return price, change, market_state, close_price, previous_close

    except Exception as e:
        logger.error(f"Error fetching extended hours price for {ticker}: {e}")
        return None, None, None, None, None


def load_tickers(source: str) -> List[str]:
    """
    Load tickers from file or comma-separated string.

    Args:
        source: Either a file path or comma-separated ticker symbols

    Returns:
        List of ticker symbols
    """
    path = Path(source)
    if path.exists():
        with open(path, "r") as f:
            tickers = [line.strip().upper() for line in f if line.strip()]
        logger.info(f"Loaded {len(tickers)} tickers from {source}")
        return tickers
    else:
        tickers = [t.strip().upper() for t in source.split(",") if t.strip()]
        logger.info(f"Parsed {len(tickers)} tickers from input")
        return tickers


def read_tickers_from_sheet(
    client: GoogleSheetsClient,
    spreadsheet_id: str,
    tab_name: str,
    ticker_col: str,
    start_row: int,
) -> List[str]:
    """
    Read ticker symbols from a column in Google Sheets.

    Args:
        client: GoogleSheetsClient instance
        spreadsheet_id: Google Sheets spreadsheet ID
        tab_name: Name of the tab to read from
        ticker_col: Column letter containing ticker symbols
        start_row: Starting row number (1-indexed)

    Returns:
        List of ticker symbols read from the sheet
    """
    try:
        range_notation = f"{tab_name}!{ticker_col}{start_row}:{ticker_col}"
        result = (
            client.service.spreadsheets()
            .values()
            .get(spreadsheetId=spreadsheet_id, range=range_notation)
            .execute()
        )
        values = result.get("values", [])
        tickers = [row[0].strip().upper() for row in values if row and row[0].strip()]
        logger.info(f"Read {len(tickers)} tickers from sheet column {ticker_col}")
        return tickers
    except Exception as e:
        logger.error(f"Failed to read tickers from sheet: {e}")
        raise


def column_letter_to_index(col: str) -> int:
    """Convert column letter (A, B, ..., Z, AA, AB, ...) to 0-based index."""
    result = 0
    for char in col.upper():
        result = result * 26 + (ord(char) - ord("A") + 1)
    return result - 1


def index_to_column_letter(index: int) -> str:
    """Convert 0-based index to column letter (A, B, ..., Z, AA, AB, ...)."""
    result = ""
    index += 1
    while index > 0:
        index, remainder = divmod(index - 1, 26)
        result = chr(ord("A") + remainder) + result
    return result


def update_prices_to_sheet(
    tickers: List[str],
    spreadsheet_id: str,
    tab_name: str,
    start_row: int,
    start_col: str,
    price_type: str = "post",
    include_change: bool = False,
    orientation: str = "vertical",
    client: Optional[GoogleSheetsClient] = None,
    quiet: bool = False,
    ticker_col: Optional[str] = None,
    close_col: Optional[str] = None,
    prev_close_col: Optional[str] = None,
    diff_col: Optional[str] = None,
    include_headers: bool = False,
    market_price_col: Optional[str] = None,
    pct_change_col: Optional[str] = None,
) -> None:
    """
    Fetch extended hours prices and update Google Sheets.

    Args:
        tickers: List of ticker symbols
        spreadsheet_id: Google Sheets spreadsheet ID
        tab_name: Name of the tab to update
        start_row: Starting row number (1-indexed)
        start_col: Starting column letter (A, B, C, ...)
        price_type: 'pre', 'post', or 'both'
        include_change: Whether to include percent change in adjacent column
        orientation: 'vertical' (one ticker per row) or 'horizontal' (one ticker per column)
        client: Optional pre-initialized GoogleSheetsClient (reused in daemon mode)
        quiet: If True, reduce logging output (for daemon mode)
        ticker_col: Optional column letter to write ticker symbols (e.g., 'A')
        close_col: Optional column letter to write today's close price (N/A if market still trading)
        prev_close_col: Optional column letter to write previous day's close price
        diff_col: Optional column letter to write % difference between extended and close price
        include_headers: Whether to write column headers in the row above data
        market_price_col: Optional column letter to write current market price (extended if available, else regular)
        pct_change_col: Optional column letter to write % change from previous close to current market price
    """
    if not quiet:
        logger.info(
            f"Fetching {price_type} market prices for {len(tickers)} tickers..."
        )

    prices_data = []
    close_data = []
    prev_close_data = []
    diff_data = []
    market_price_data = []
    pct_change_data = []
    for ticker in tickers:
        price, change, market_state, close_price, previous_close = (
            get_extended_hours_price(ticker, price_type)
        )
        if price is not None:
            if include_change:
                prices_data.append([price, change if change is not None else ""])
            else:
                prices_data.append([price])
            if not quiet:
                logger.info(
                    f"{ticker}: ${price:.2f} ({change:+.2f}% | {market_state})"
                    if change
                    else f"{ticker}: ${price:.2f}"
                )
        else:
            if include_change:
                prices_data.append(["N/A", ""])
            else:
                prices_data.append(["N/A"])
            logger.warning(f"{ticker}: Price not available")

        is_market_closed = market_state not in ("REGULAR", "PRE")
        if is_market_closed and close_price is not None:
            close_data.append([close_price])
        else:
            close_data.append(["N/A"])

        prev_close_data.append(
            [previous_close if previous_close is not None else "N/A"]
        )

        if price is not None and close_price is not None and close_price != 0:
            pct_diff = round(((price - close_price) / close_price) * 100, 2)
            diff_data.append([pct_diff])
        else:
            diff_data.append(["N/A"])

        current_market_price = price if price is not None else close_price
        market_price_data.append(
            [current_market_price if current_market_price is not None else "N/A"]
        )

        if (
            current_market_price is not None
            and previous_close is not None
            and previous_close != 0
        ):
            pct_from_prev = round(
                ((current_market_price - previous_close) / previous_close) * 100, 2
            )
            pct_change_data.append([pct_from_prev])
        else:
            pct_change_data.append(["N/A"])

    if orientation == "horizontal":
        if include_change:
            flat_prices = []
            for p in prices_data:
                flat_prices.extend(p)
            prices_data = [flat_prices]
        else:
            prices_data = [[p[0] for p in prices_data]]
        close_data = [[c[0] for c in close_data]]
        prev_close_data = [[p[0] for p in prev_close_data]]
        diff_data = [[d[0] for d in diff_data]]
        market_price_data = [[m[0] for m in market_price_data]]
        pct_change_data = [[p[0] for p in pct_change_data]]

    try:
        if client is None:
            client = create_sheets_client()

        start_cell = f"{start_col}{start_row}"

        client.get_or_create_sheet_tab(spreadsheet_id, tab_name)

        batch_data = []

        if include_headers and start_row > 1:
            header_row = start_row - 1
            if ticker_col:
                batch_data.append(
                    {
                        "range": f"{tab_name}!{ticker_col}{header_row}",
                        "values": [["Ticker"]],
                    }
                )
            if close_col:
                batch_data.append(
                    {
                        "range": f"{tab_name}!{close_col}{header_row}",
                        "values": [["Close Price"]],
                    }
                )
            if prev_close_col:
                batch_data.append(
                    {
                        "range": f"{tab_name}!{prev_close_col}{header_row}",
                        "values": [["Previous Close Price"]],
                    }
                )
            batch_data.append(
                {
                    "range": f"{tab_name}!{start_col}{header_row}",
                    "values": [["Extended Hour Price"]],
                }
            )
            if diff_col:
                batch_data.append(
                    {
                        "range": f"{tab_name}!{diff_col}{header_row}",
                        "values": [["Percentage Change"]],
                    }
                )
            if market_price_col:
                batch_data.append(
                    {
                        "range": f"{tab_name}!{market_price_col}{header_row}",
                        "values": [["Market Price(with extended hour)"]],
                    }
                )
            if pct_change_col:
                batch_data.append(
                    {
                        "range": f"{tab_name}!{pct_change_col}{header_row}",
                        "values": [["% Change Since Last Close"]],
                    }
                )

        if ticker_col:
            if orientation == "vertical":
                ticker_data = [[t] for t in tickers]
            else:
                ticker_data = [tickers]
            ticker_range = f"{tab_name}!{ticker_col}{start_row}"
            batch_data.append({"range": ticker_range, "values": ticker_data})

        batch_data.append({"range": f"{tab_name}!{start_cell}", "values": prices_data})

        if close_col:
            close_range = f"{tab_name}!{close_col}{start_row}"
            batch_data.append({"range": close_range, "values": close_data})

        if prev_close_col:
            prev_close_range = f"{tab_name}!{prev_close_col}{start_row}"
            batch_data.append({"range": prev_close_range, "values": prev_close_data})

        if diff_col:
            diff_range = f"{tab_name}!{diff_col}{start_row}"
            batch_data.append({"range": diff_range, "values": diff_data})

        if market_price_col:
            market_price_range = f"{tab_name}!{market_price_col}{start_row}"
            batch_data.append(
                {"range": market_price_range, "values": market_price_data}
            )

        if pct_change_col:
            pct_change_range = f"{tab_name}!{pct_change_col}{start_row}"
            batch_data.append({"range": pct_change_range, "values": pct_change_data})

        body = {"valueInputOption": "RAW", "data": batch_data}

        result = (
            client.service.spreadsheets()
            .values()
            .batchUpdate(spreadsheetId=spreadsheet_id, body=body)
            .execute()
        )

        updated_cells = result.get("totalUpdatedCells", 0)
        if not quiet:
            logger.info(
                f"Successfully updated {updated_cells} cells in '{tab_name}' starting at {start_cell}"
            )
            logger.info(
                f"Spreadsheet: https://docs.google.com/spreadsheets/d/{spreadsheet_id}"
            )

    except Exception as e:
        logger.error(f"Failed to update Google Sheets: {e}")
        raise


def run_daemon(
    tickers: List[str],
    spreadsheet_id: str,
    tab_name: str,
    start_row: int,
    start_col: str,
    price_type: str,
    include_change: bool,
    orientation: str,
    interval: float,
    ticker_col: Optional[str] = None,
    close_col: Optional[str] = None,
    prev_close_col: Optional[str] = None,
    diff_col: Optional[str] = None,
    include_headers: bool = False,
    market_price_col: Optional[str] = None,
    pct_change_col: Optional[str] = None,
    read_tickers_from_col: Optional[str] = None,
    on_new_tickers_cmd: Optional[str] = None,
) -> None:
    """
    Run in daemon mode, updating prices at regular intervals.

    Args:
        tickers: List of ticker symbols
        spreadsheet_id: Google Sheets spreadsheet ID
        tab_name: Name of the tab to update
        start_row: Starting row number (1-indexed)
        start_col: Starting column letter
        price_type: 'pre', 'post', or 'both'
        include_change: Whether to include percent change
        orientation: 'vertical' or 'horizontal'
        interval: Update interval in seconds
        ticker_col: Optional column letter to write ticker symbols
        close_col: Optional column letter to write today's close price
        prev_close_col: Optional column letter to write previous day's close price
        diff_col: Optional column letter to write % difference
        include_headers: Whether to write column headers (only on first update)
        market_price_col: Optional column letter to write current market price
        pct_change_col: Optional column letter to write % change from previous close
        read_tickers_from_col: If set, re-read tickers from this column on each update
        on_new_tickers_cmd: If set, run this command when new tickers are detected
    """
    global _shutdown_requested

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    logger.info(f"Starting daemon mode - updating every {interval} seconds")
    logger.info(f"Initial tickers: {', '.join(tickers)}")
    if read_tickers_from_col:
        logger.info(
            f"Will re-read tickers from column {read_tickers_from_col} on each update"
        )
    logger.info("Press Ctrl+C to stop")
    logger.info(f"Spreadsheet: https://docs.google.com/spreadsheets/d/{spreadsheet_id}")

    client = create_sheets_client()

    update_count = 0
    current_tickers = tickers
    running_subprocess = None  # Track running subprocess
    running_subprocess_log = None  # Track log file handle
    running_subprocess_start = None  # Track start time for timeout
    subprocess_queue = []  # Queue for pending commands
    subprocess_timeout = 30 * 60  # 30 minutes timeout

    def start_subprocess_from_queue(timestamp):
        """Start the next subprocess from queue if available."""
        nonlocal running_subprocess, running_subprocess_log, running_subprocess_start
        if subprocess_queue and running_subprocess is None:
            cmd = subprocess_queue.pop(0)
            logger.info(f"[{timestamp}] Starting queued command...")
            logger.info(f"[{timestamp}] Command: {cmd}")
            try:
                log_filename = (
                    f"earnings_script_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
                )
                running_subprocess_log = open(log_filename, "w")
                running_subprocess = subprocess.Popen(
                    cmd,
                    shell=True,
                    stdout=running_subprocess_log,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
                running_subprocess_start = time.time()
                logger.info(
                    f"[{timestamp}] Earnings script started in background, output: {log_filename}"
                )
                if subprocess_queue:
                    logger.info(
                        f"[{timestamp}] Queue status: {len(subprocess_queue)} command(s) pending"
                    )
            except Exception as e:
                logger.error(f"[{timestamp}] Failed to start earnings script: {e}")
                if running_subprocess_log:
                    running_subprocess_log.close()
                    running_subprocess_log = None

    while not _shutdown_requested:
        update_count += 1
        timestamp = datetime.now().strftime("%H:%M:%S")

        try:
            # Check subprocess status: timeout or completion
            if running_subprocess is not None:
                if running_subprocess.poll() is not None:
                    # Subprocess finished
                    logger.info(f"[{timestamp}] Earnings script completed")
                    if running_subprocess_log:
                        running_subprocess_log.close()
                        running_subprocess_log = None
                    running_subprocess = None
                    running_subprocess_start = None
                    # Start next from queue if available
                    start_subprocess_from_queue(timestamp)
                elif (
                    running_subprocess_start
                    and (time.time() - running_subprocess_start) > subprocess_timeout
                ):
                    # Timeout - kill the subprocess
                    logger.warning(
                        f"[{timestamp}] Earnings script exceeded 30 min timeout, killing..."
                    )
                    running_subprocess.kill()
                    if running_subprocess_log:
                        running_subprocess_log.close()
                        running_subprocess_log = None
                    running_subprocess = None
                    running_subprocess_start = None
                    # Start next from queue if available
                    start_subprocess_from_queue(timestamp)

            if read_tickers_from_col:
                new_tickers = read_tickers_from_sheet(
                    client=client,
                    spreadsheet_id=spreadsheet_id,
                    tab_name=tab_name,
                    ticker_col=read_tickers_from_col,
                    start_row=start_row,
                )
                if new_tickers != current_tickers:
                    added = set(new_tickers) - set(current_tickers)
                    removed = set(current_tickers) - set(new_tickers)
                    if added:
                        logger.info(
                            f"[{timestamp}] New tickers added: {', '.join(added)}"
                        )
                    if removed:
                        logger.info(
                            f"[{timestamp}] Tickers removed: {', '.join(removed)}"
                        )
                    current_tickers = new_tickers
                    tickers_file = "tickers_from_spreadsheet.txt"
                    with open(tickers_file, "w") as f:
                        f.write(",".join(current_tickers))
                    logger.info(
                        f"[{timestamp}] Updated {tickers_file} with {len(current_tickers)} tickers"
                    )

                    if added and on_new_tickers_cmd:
                        today_str = datetime.now().strftime("%Y-%m-%d")
                        cmd = on_new_tickers_cmd.replace("{date}", today_str)

                        if running_subprocess is None:
                            # No subprocess running, start immediately
                            subprocess_queue.append(cmd)
                            start_subprocess_from_queue(timestamp)
                        else:
                            # Add to queue
                            subprocess_queue.append(cmd)
                            logger.info(
                                f"[{timestamp}] Command queued (subprocess running). Queue size: {len(subprocess_queue)}"
                            )

            if not current_tickers:
                logger.warning(f"[{timestamp}] No tickers to update, skipping...")
            else:
                update_prices_to_sheet(
                    tickers=current_tickers,
                    spreadsheet_id=spreadsheet_id,
                    tab_name=tab_name,
                    start_row=start_row,
                    start_col=start_col,
                    price_type=price_type,
                    include_change=include_change,
                    orientation=orientation,
                    client=client,
                    quiet=True,
                    ticker_col=ticker_col,
                    close_col=close_col,
                    prev_close_col=prev_close_col,
                    diff_col=diff_col,
                    include_headers=(include_headers and update_count == 1),
                    market_price_col=market_price_col,
                    pct_change_col=pct_change_col,
                )
                # Build status message with subprocess info
                status_parts = [
                    f"Update #{update_count} completed ({len(current_tickers)} tickers)"
                ]
                if running_subprocess is not None and running_subprocess_start:
                    elapsed_mins = int((time.time() - running_subprocess_start) / 60)
                    elapsed_secs = int((time.time() - running_subprocess_start) % 60)
                    status_parts.append(
                        f"subprocess running {elapsed_mins}m{elapsed_secs}s"
                    )
                if subprocess_queue:
                    status_parts.append(f"queue: {len(subprocess_queue)} pending")
                logger.info(f"[{timestamp}] {' | '.join(status_parts)}")

        except Exception as e:
            logger.error(f"[{timestamp}] Update #{update_count} failed: {e}")

        sleep_start = time.time()
        while not _shutdown_requested and (time.time() - sleep_start) < interval:
            time.sleep(0.1)

    # Cleanup: close log file if still open
    if running_subprocess_log:
        running_subprocess_log.close()

    if subprocess_queue:
        logger.warning(
            f"Daemon stopped with {len(subprocess_queue)} queued command(s) not executed"
        )

    logger.info(f"Daemon stopped after {update_count} updates")


def main():
    parser = argparse.ArgumentParser(
        description="Update extended hours stock prices to Google Sheets",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic: Update post-market prices for tickers vertically starting at B2
  python update_extended_hours_prices.py \\
    --tickers "AAPL,GOOGL,MSFT" \\
    --spreadsheet-id 1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms \\
    --tab-name "Prices" \\
    --row 2 \\
    --col B

  # Pre-market prices from a file, horizontally with change %
  python update_extended_hours_prices.py \\
    --tickers tickers.txt \\
    --spreadsheet-id 1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms \\
    --tab-name "PreMarket" \\
    --row 1 \\
    --col A \\
    --price-type pre \\
    --include-change \\
    --orientation horizontal

  # Full example with all columns:
  # A: Ticker, B: Previous Close, C: Close Price, D: Extended Hour Price,
  # E: Percentage Change (vs regular), F: Market Price, G: % Change Since Last Close
  python update_extended_hours_prices.py \\
    --tickers "AAPL,GOOGL,MSFT" \\
    --spreadsheet-id 1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms \\
    --tab-name "Prices" \\
    --row 2 --col D \\
    --ticker-col A \\
    --prev-close-col B \\
    --close-col C \\
    --diff-col E \\
    --market-price-col F \\
    --pct-change-col G \\
    --include-headers

  # Daemon mode with all columns (headers written on first update only)
  python update_extended_hours_prices.py \\
    --tickers "AAPL,TSLA,NVDA" \\
    --spreadsheet-id 1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms \\
    --tab-name "LivePrices" \\
    --row 2 --col D \\
    --ticker-col A \\
    --prev-close-col B \\
    --close-col C \\
    --diff-col E \\
    --market-price-col F \\
    --pct-change-col G \\
    --include-headers \\
    --daemon --interval 10

  # Read tickers from spreadsheet column A (no --tickers needed)
  # Useful when the spreadsheet already has a list of tickers
  python update_extended_hours_prices.py \\
    --spreadsheet-id 1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms \\
    --tab-name "Prices" \\
    --row 2 --col D \\
    --ticker-col A \\
    --prev-close-col B \\
    --close-col C \\
    --market-price-col E \\
    --pct-change-col F

  # Daemon mode: auto-trigger earnings script when new tickers are added
  python update_extended_hours_prices.py \\
    --spreadsheet-id 1UDqEa__FQPbAFWLSJ69zKDJwtaEbym_o0r3N3GElDIA \\
    --tab-name "Prices" \\
    --row 2 --col D \\
    --ticker-col A \\
    --daemon --interval 10 \\
    --on-new-tickers-cmd "cd tradingview_scraper && python run_earnings_to_sheets.py \\
      --tickers-file ../tickers_from_spreadsheet.txt \\
      --spreadsheet-id 1UDqEa__FQPbAFWLSJ69zKDJwtaEbym_o0r3N3GElDIA \\
      --date {date} --tab-name Earnings_Data --quarter-mode reported --concurrency 5"

  # Tickers file format (one ticker per line):
  # AAPL
  # GOOGL
  # MSFT

Ticker Source (one of these is required):
  --tickers            Provide tickers via command line or file
  --ticker-col         Read tickers from this column in the spreadsheet
                       (if --tickers is not provided)
                       Note: When reading from sheet, tickers are also saved to
                       "tickers_from_spreadsheet.txt" (comma-separated) for use
                       by other scripts like run_earnings_to_sheets.py

Column Descriptions:
  --col (required)       Extended Hour Price (pre/post market price)
  --ticker-col           Ticker symbol
  --prev-close-col       Previous day's close price (always available)
  --close-col            Today's close price (N/A if market still trading)
  --diff-col             % change: (extended - regularMarketPrice) / regularMarketPrice
  --market-price-col     Current market price (extended if available, else regular)
  --pct-change-col       % change: (marketPrice - previousClose) / previousClose
        """,
    )

    parser.add_argument(
        "--tickers",
        default=None,
        help="Comma-separated tickers or path to file with one ticker per line. "
        "If not provided, tickers will be read from --ticker-col in the spreadsheet.",
    )

    parser.add_argument(
        "--spreadsheet-id",
        required=True,
        help="Google Sheets spreadsheet ID (from the URL)",
    )

    parser.add_argument(
        "--tab-name",
        default="Sheet1",
        help="Name of the tab to update (default: Sheet1)",
    )

    parser.add_argument(
        "--row", type=int, required=True, help="Starting row number (1-indexed)"
    )

    parser.add_argument(
        "--col", required=True, help="Starting column letter for prices (A, B, C, ...)"
    )

    parser.add_argument(
        "--ticker-col",
        default=None,
        help="Column letter to write ticker symbols (e.g., A). If not specified, tickers are not written.",
    )

    parser.add_argument(
        "--close-col",
        default=None,
        help="Column letter to write today's close price (N/A if market still trading).",
    )

    parser.add_argument(
        "--prev-close-col",
        default=None,
        help="Column letter to write previous day's close price.",
    )

    parser.add_argument(
        "--diff-col",
        default=None,
        help="Column letter to write %% difference between extended hours and close price (e.g., D).",
    )

    parser.add_argument(
        "--market-price-col",
        default=None,
        help="Column letter to write current market price (extended if available, else regular).",
    )

    parser.add_argument(
        "--pct-change-col",
        default=None,
        help="Column letter to write %% change from previous close to current market price.",
    )

    parser.add_argument(
        "--include-headers",
        action="store_true",
        help="Write column headers (Ticker, Close Price, Extended Hour Price, Percentage Change, Market Price, %% Change Since Last Close) in the row above data",
    )

    parser.add_argument(
        "--price-type",
        choices=["pre", "post", "both"],
        default="post",
        help="Price type: pre (pre-market), post (after-hours), both (default: post)",
    )

    parser.add_argument(
        "--include-change",
        action="store_true",
        help="Include percent change in adjacent column/cell",
    )

    parser.add_argument(
        "--orientation",
        choices=["vertical", "horizontal"],
        default="vertical",
        help="Layout: vertical (one ticker per row) or horizontal (one ticker per column)",
    )

    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable verbose logging"
    )

    parser.add_argument(
        "--daemon",
        "-d",
        action="store_true",
        help="Run in daemon mode, continuously updating at specified interval",
    )

    parser.add_argument(
        "--interval",
        type=float,
        default=5.0,
        help="Update interval in seconds for daemon mode (default: 5)",
    )

    parser.add_argument(
        "--on-new-tickers-cmd",
        type=str,
        default=None,
        help="Command to run when new tickers are detected (daemon mode only). "
        "Use {date} as placeholder for today's date. "
        "Example: 'python run_earnings_to_sheets.py --tickers-file tickers_from_spreadsheet.txt --date {date}'",
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    tickers_from_sheet = False
    if args.tickers:
        tickers = load_tickers(args.tickers)
    elif args.ticker_col:
        logger.info("Reading tickers from spreadsheet...")
        client = create_sheets_client()
        tickers = read_tickers_from_sheet(
            client=client,
            spreadsheet_id=args.spreadsheet_id,
            tab_name=args.tab_name,
            ticker_col=args.ticker_col,
            start_row=args.row,
        )
        tickers_from_sheet = True
        if tickers:
            tickers_file = "tickers_from_spreadsheet.txt"
            with open(tickers_file, "w") as f:
                f.write(",".join(tickers))
            logger.info(f"Saved {len(tickers)} tickers to {tickers_file}")
    else:
        logger.error(
            "No tickers provided. Use --tickers or --ticker-col to specify tickers."
        )
        sys.exit(1)

    # In daemon mode with sheet as source, allow starting with empty tickers
    # (the daemon will poll the sheet and pick up tickers when they appear)
    if not tickers:
        if args.daemon and tickers_from_sheet:
            logger.warning(
                "No tickers found in spreadsheet. "
                "Daemon will start and poll for tickers..."
            )
        else:
            logger.error("No tickers found")
            sys.exit(1)

    # Don't write to ticker_col if tickers were read from sheet (it's the source of truth)
    write_ticker_col = None if tickers_from_sheet else args.ticker_col
    # Re-read tickers from sheet in daemon mode if tickers came from sheet
    read_tickers_col = args.ticker_col if tickers_from_sheet else None

    if args.daemon:
        run_daemon(
            tickers=tickers,
            spreadsheet_id=args.spreadsheet_id,
            tab_name=args.tab_name,
            start_row=args.row,
            start_col=args.col,
            price_type=args.price_type,
            include_change=args.include_change,
            orientation=args.orientation,
            interval=args.interval,
            ticker_col=write_ticker_col,
            close_col=args.close_col,
            prev_close_col=args.prev_close_col,
            diff_col=args.diff_col,
            include_headers=args.include_headers,
            market_price_col=args.market_price_col,
            pct_change_col=args.pct_change_col,
            read_tickers_from_col=read_tickers_col,
            on_new_tickers_cmd=args.on_new_tickers_cmd,
        )
    else:
        update_prices_to_sheet(
            tickers=tickers,
            spreadsheet_id=args.spreadsheet_id,
            tab_name=args.tab_name,
            start_row=args.row,
            start_col=args.col,
            price_type=args.price_type,
            include_change=args.include_change,
            orientation=args.orientation,
            ticker_col=write_ticker_col,
            close_col=args.close_col,
            prev_close_col=args.prev_close_col,
            diff_col=args.diff_col,
            include_headers=args.include_headers,
            market_price_col=args.market_price_col,
            pct_change_col=args.pct_change_col,
        )


if __name__ == "__main__":
    main()
