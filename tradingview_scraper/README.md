# TradingView Scraper

This folder contains tools for scraping earnings data from TradingView and uploading to Google Sheets.

## Main Scripts

### generate_earnings_analysis.py

Generate comprehensive earnings analysis CSV by combining TradingView API data with scraped historical data.

```bash
# Today's earnings
python generate_earnings_analysis.py

# Specific date
python generate_earnings_analysis.py --date 2025-01-15

# Expand date range (+/- 3 days around the date)
python generate_earnings_analysis.py --date 2025-01-15 --expand-to-near-by-days 3

# Filter to specific tickers
python generate_earnings_analysis.py --tickers "AAPL, MSFT, GOOGL"

# Use 5 concurrent scraping sessions
python generate_earnings_analysis.py --concurrency 5

# Use reported quarter mode (last reported quarter as anchor)
python generate_earnings_analysis.py --quarter-mode reported
```

**Options:**
| Option | Description |
|--------|-------------|
| `--date` | Date to fetch earnings for (YYYY-MM-DD). Default: today |
| `--expand-to-near-by-days` | Expand date coverage by N days on both sides |
| `--tickers` | Comma-separated list of tickers to filter |
| `--limit` | Limit number of tickers (for testing) |
| `--concurrency` | Number of concurrent scraping sessions (default: 3) |
| `--quarter-mode` | `forecast` (default) or `reported` |
| `--output` | Output CSV filename |
| `--no-headless` | Show browser during scraping |

### run_earnings_to_sheets.py

Generate earnings analysis and upload directly to Google Sheets.

```bash
# Basic usage
python run_earnings_to_sheets.py \
  --spreadsheet-id YOUR_SHEET_ID \
  --tab-name "Earnings_Data"

# Use tickers from a file
python run_earnings_to_sheets.py \
  --tickers-file ../tickers_from_spreadsheet.txt \
  --spreadsheet-id YOUR_SHEET_ID \
  --tab-name "Earnings_Data"

# Only process new tickers (skip existing ones in column A)
python run_earnings_to_sheets.py \
  --tickers-file ../tickers_from_spreadsheet.txt \
  --spreadsheet-id YOUR_SHEET_ID \
  --tab-name "Earnings_Data" \
  --skip-existing-tickers-col A

# Expand date range
python run_earnings_to_sheets.py \
  --date 2025-01-15 \
  --expand-to-near-by-days 3 \
  --spreadsheet-id YOUR_SHEET_ID
```

**Additional Options:**
| Option | Description |
|--------|-------------|
| `--tickers-file` | Path to file with tickers (comma-separated or one per line) |
| `--skip-existing-tickers-col` | Column letter with existing tickers to skip |
| `--skip-existing-tickers-tab` | Tab name to read existing tickers from |
| `--no-clear` | Append mode (don't clear existing data) |
| `--keep-csv` | Keep local CSV file after upload |
| `--skip-upload` | Generate CSV only, don't upload |

### quarterly_annual_collector.py

Collect quarterly and yearly Revenue/EPS data (historical + forecast) for a list of tickers directly from TradingView's forecast page, and persist it to a local YAML store that gets extended (not replaced) on every rerun.

```bash
# Collect data for a list of tickers
python quarterly_annual_collector.py --tickers "LLY, AAPL, MSFT"

# Read tickers from a file (comma-separated or one per line)
python quarterly_annual_collector.py --tickers-file ../tickers_from_spreadsheet.txt

# Show the browser during scraping (for debugging)
python quarterly_annual_collector.py --tickers LLY --no-headless

# Non-interactive rerun: always take the freshly scraped value on conflicts
python quarterly_annual_collector.py --tickers LLY --on-reported-conflict overwrite

# Non-interactive rerun: always keep whatever is already stored on conflicts
python quarterly_annual_collector.py --tickers LLY --on-reported-conflict keep
```

**Options:**
| Option | Description |
|--------|-------------|
| `--tickers` | Comma-separated list of tickers (e.g. `"LLY, AAPL, MSFT"`) |
| `--tickers-file` | Path to a file with tickers (comma-separated or one per line) |
| `--no-headless` | Show browser during scraping (for debugging) |
| `--on-reported-conflict` | `ask` (default, prompt interactively), `overwrite`, or `keep` — see [Data Storage](#data-storage) below |

**What it does:**
- Resolves each ticker's exchange automatically via TradingView's symbol search (the forecast page 404s on the wrong exchange rather than redirecting)
- Scrapes as many historical quarters/years and forward estimates as TradingView's free tier exposes for that ticker (typically ~7-8 quarters and ~5 years, but this varies)
- Relabels periods using the company's own fiscal reporting quarter/year, not the calendar quarter (e.g. `Q3 '24` → `Q3 2024`, `2024` → `2024 Yearly`)
- Also scrapes the reporting currency (e.g. `USD`) shown next to the ticker symbol
- Prints a per-ticker summary of Revenue and EPS (quarterly/annual, historical/forecast)
- Logs a **Missing Data Log** for any metric/period-type combination that came back completely empty
- Logs a **Data Store Merge Log** summarizing every value added, overwritten, kept, or cleaned up during the merge (see below)

## Data Storage

Every run of `quarterly_annual_collector.py` merges its freshly scraped data into a local YAML file at:

```
company_earnings_data/<EXCHANGE>_<TICKER>/earning.yaml
```

e.g. `company_earnings_data/NYSE_LLY/earning.yaml`. Reruns **extend** this file rather than overwriting it, following these rules:

- **Reported (actual) data points** — quarterly/annual historicals. New periods are added automatically. If a period already has a stored value and a rerun scrapes a *different* value for it (e.g. a restatement), you'll be prompted:
  ```
  ⚠ Discrepancy for LLY revenue quarterly Q1 2026: stored=99999.0, scraped=19800.0
    Overwrite stored value with scraped value? [y/N]:
  ```
  Use `--on-reported-conflict overwrite` or `--on-reported-conflict keep` to resolve these non-interactively (e.g. in scripted/CI runs) instead of prompting.
- **Forecast data points** — quarterly/annual estimates. These change often, so they're always overwritten automatically on every run — but every change is logged in the Data Store Merge Log so you can see what shifted.
- **Forecast → reported transitions** — once a period that used to be a forecast has reported data available, the stale forecast entry for that period is automatically removed from the store.
- **Currency** — recorded on first scrape; if a later scrape ever returns a different currency for the same ticker, it's flagged in the log and the originally stored value is kept (this generally shouldn't happen and is worth investigating if it does).

## Helper Modules

- **earnings_api_helper.py** - Fetch earnings calendar data from TradingView API
- **financial_data_helper.py** - Scrape detailed financial data from TradingView pages
- **earnings_data_store.py** - Load/merge/save persisted Revenue/EPS data in `company_earnings_data/`
- **csv_generator.py** - Build and save CSV output

## Data Extracted

- EPS estimates and actuals (current quarter)
- Revenue estimates and actuals (current quarter)
- Year-over-year comparisons (historical data)
- Company info (sector, industry, market cap)

## Requirements

```bash
pip install selenium beautifulsoup4 requests
```

Google Sheets integration requires credentials configured in `.env`:
- `GOOGLE_SHEETS_CREDENTIALS_PATH` or `GOOGLE_SHEETS_CREDENTIALS_JSON`
