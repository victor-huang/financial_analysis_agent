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

## Helper Modules

- **earnings_api_helper.py** - Fetch earnings calendar data from TradingView API
- **financial_data_helper.py** - Scrape detailed financial data from TradingView pages
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
