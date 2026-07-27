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

# Scrape 5 tickers in parallel (requires a non-interactive conflict mode)
python quarterly_annual_collector.py --tickers "LLY, AAPL, MSFT, STLD, PAC" \
  --concurrency 5 --on-reported-conflict overwrite
```

**Options:**
| Option | Description |
|--------|-------------|
| `--tickers` | Comma-separated list of tickers (e.g. `"LLY, AAPL, MSFT"`) |
| `--tickers-file` | Path to a file with tickers (comma-separated or one per line) |
| `--no-headless` | Show browser during scraping (for debugging) |
| `--on-reported-conflict` | `ask` (default, prompt interactively), `overwrite`, or `keep` — see [Data Storage](#data-storage) below |
| `--concurrency` | Number of tickers to scrape in parallel (default: 1). Requires `--on-reported-conflict overwrite\|keep` — concurrent interactive prompts can't be resolved safely |

**What it does:**
- Resolves each ticker's exchange automatically via TradingView's symbol search (the forecast page 404s on the wrong exchange rather than redirecting)
- Scrapes as many historical quarters/years and forward estimates as TradingView's free tier exposes for that ticker (typically ~7-8 quarters and ~5 years, but this varies)
- Relabels periods using the company's own fiscal reporting quarter/year, not the calendar quarter (e.g. `Q3 '24` → `Q3 2024`, `2024` → `2024 Yearly`)
- Also scrapes the reporting currency (e.g. `USD`) shown next to the ticker symbol
- Prints a per-ticker summary of Revenue and EPS (quarterly/annual, historical/forecast)
- Logs a **Missing Data Log** for any metric/period-type combination that came back completely empty
- Logs a **Data Store Merge Log** summarizing every value added, overwritten, kept, or cleaned up during the merge (see below)

### export_earning_store_to_sheets.py

Upload the local `company_earnings_data/` store (collected by `quarterly_annual_collector.py`) to Google Sheets — one row per ticker, one column per period.

```bash
# Export tickers already collected in the local store
python export_earning_store_to_sheets.py \
  --tickers "STLD, PAC" \
  --spreadsheet-id YOUR_SHEET_ID \
  --tab-name "ERN DataBase"

# Read tickers from a file
python export_earning_store_to_sheets.py \
  --tickers-file ../tickers_from_spreadsheet.txt \
  --spreadsheet-id YOUR_SHEET_ID \
  --tab-name "ERN DataBase"

# Re-scrape and merge each ticker first, then export
python export_earning_store_to_sheets.py \
  --tickers "STLD, PAC" --refresh \
  --spreadsheet-id YOUR_SHEET_ID --tab-name "ERN DataBase"

# Preview the CSV that would be uploaded, without touching the sheet
python export_earning_store_to_sheets.py \
  --tickers "STLD, PAC" --skip-upload --keep-csv \
  --spreadsheet-id YOUR_SHEET_ID --tab-name "ERN DataBase"
```

**Options:**
| Option | Description |
|--------|-------------|
| `--tickers` | Comma-separated list of tickers |
| `--tickers-file` | Path to a file with tickers (comma-separated or one per line) |
| `--spreadsheet-id` | Google Sheets spreadsheet ID (required) |
| `--tab-name` | Tab to write to (default: `Earnings_Store`) |
| `--refresh` | Re-scrape TradingView and merge into the store before exporting (default: export the store as-is) |
| `--no-headless` | Show browser during scraping (only relevant with `--refresh`) |
| `--on-reported-conflict` | `ask`/`overwrite`/`keep` — passed through to the collector, only relevant with `--refresh` |
| `--output` | Local CSV filename (default: `earning_store_export.csv`) |
| `--keep-csv` | Keep the local CSV file after uploading |
| `--skip-upload` | Generate CSV only, don't upload |

**How the columns are determined:** see [Uploading to Google Sheets](#uploading-to-google-sheets) below — this script maps to whatever header the target tab already has, rather than a fixed layout.

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
- **Estimate retention after reporting** — TradingView shows the original analyst estimate alongside the reported value even for periods that have already reported (useful for beat/miss comparisons), so the estimate is kept in the forecast bucket permanently rather than being discarded once a period is reported.
- **Currency** — recorded on first scrape; if a later scrape ever returns a different currency for the same ticker, it's flagged in the log and the originally stored value is kept (this generally shouldn't happen and is worth investigating if it does).

## Helper Modules

- **earnings_api_helper.py** - Fetch earnings calendar data from TradingView API
- **financial_data_helper.py** - Scrape detailed financial data from TradingView pages
- **earnings_data_store.py** - Load/merge/save persisted Revenue/EPS data in `company_earnings_data/`
- **csv_generator.py** - Build and save CSV output
- **earning_store_export.py** - Build the generic wide-format CSV rows for a brand new (empty) sheet tab
- **sheet_column_mapping.py** - Parse an existing sheet's header row into per-column resolvers for `export_earning_store_to_sheets.py`

## Data Extracted

- EPS estimates and actuals (current quarter)
- Revenue estimates and actuals (current quarter)
- Year-over-year comparisons (historical data)
- Company info (sector, industry, market cap)

## Uploading to Google Sheets

### 1. Set up credentials

Google Sheets uploads authenticate with a service account. In `.env` (or `.env.local`), set one of:
- `GOOGLE_SHEETS_CREDENTIALS_PATH` — path to a service account JSON key file
- `GOOGLE_SHEETS_CREDENTIALS_JSON` — the service account JSON contents inline

Then **share the target spreadsheet** with the service account's `client_email` (found inside the JSON key file), giving it Editor access — without this, every request fails with a permissions error even though the credentials themselves are valid.

### 2. Pick the right upload script

There are two independent upload paths, for two different data pipelines — use whichever matches the data you've collected:

| | `run_earnings_to_sheets.py` | `export_earning_store_to_sheets.py` |
|---|---|---|
| Data source | `generate_earnings_analysis.py` (current-quarter API + scraper) | `company_earnings_data/` store (`quarterly_annual_collector.py`) |
| Layout | One fixed set of columns (`csv_generator.get_csv_headers()`) | Matches whatever header the target tab already has |
| New tab (no header yet) | Writes the fixed column set | Writes a generic wide layout (one column per period) to bootstrap it |
| Rerun behavior | Appends rows if headers match, otherwise replaces all data | Updates each ticker's existing row in place; only appends rows for tickers not already present |

### 3. How export_earning_store_to_sheets.py maps columns

Rather than hardcoding column names, this script **reads the target tab's existing header row live** and parses each column (via `sheet_column_mapping.py`) into a resolver — static fields (`ticker`, `Company name`, `Market segment`, `Market Cap (B)`, ...), quarterly/annual EPS+Revenue columns (`Q3 24 EPS`, `2024 Rev`), and estimate-vs-actual variants (`Q2 26 EPS Est.` / `Q2 26 EPS act`). This means:

- A sheet's column names, order, or even typos (a stray trailing space, inconsistent punctuation) are matched exactly — the upload won't silently create a differently-shaped duplicate header.
- Adding a brand new target sheet with its own column conventions needs **no code changes**, as long as it follows a recognized naming pattern; only a genuinely new convention (e.g. a different way of writing "estimate") needs a one-line addition to `sheet_column_mapping.py`.
- Any header cell that can't be parsed is left blank on every row and reported as an "unrecognized column" warning, so nothing fails silently.

### 4. Typical workflow

```bash
# Step 1: scrape and persist to the local store
python quarterly_annual_collector.py --tickers "STLD, PAC" --on-reported-conflict overwrite

# Step 2: upload the store to the sheet
python export_earning_store_to_sheets.py \
  --tickers "STLD, PAC" \
  --spreadsheet-id YOUR_SHEET_ID \
  --tab-name "ERN DataBase"
```

Rerunning both commands later (e.g. after new earnings are reported) is safe: the collector merges new data into the same YAML files, and the export updates each ticker's existing sheet row in place rather than appending a duplicate.

## Requirements

```bash
pip install selenium beautifulsoup4 requests pyyaml
```
