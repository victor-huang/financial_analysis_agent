# Financial Analysis Agent

A Python-based tool for analyzing company financial data and social media sentiment using state-of-the-art LLMs.

## Features
- Fetch and analyze financial data (stock prices, fundamentals, etc.)
- Collect and process social media data
- Perform sentiment analysis using LLMs
- Generate insights and visualizations
- Configurable data sources and analysis parameters

## Setup
1. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Set up environment variables:
   ```bash
   cp .env.example .env
   # Edit .env with your API keys
   ```

## Usage

### Financial Analysis
```bash
# Full report (financial + social + LLM summary)
python -m financial_analysis_agent.analyze AAPL --analysis-type full --verbose

# Financials only (no social or LLM), optionally save to file
python -m financial_analysis_agent.analyze AAPL --analysis-type financial --verbose --output aapl.json
```

### Extended Hours Price Tracker

Update stock prices (including pre/post market) to Google Sheets:

```bash
# Basic usage - update extended hours prices
python update_extended_hours_prices.py \
  --tickers "AAPL,GOOGL,MSFT" \
  --spreadsheet-id YOUR_SHEET_ID \
  --tab-name "Prices" \
  --row 2 --col D

# Read tickers from spreadsheet column A (auto-detect ticker list)
python update_extended_hours_prices.py \
  --spreadsheet-id YOUR_SHEET_ID \
  --tab-name "Prices" \
  --row 2 --col D \
  --ticker-col A \
  --prev-close-col B \
  --close-col C \
  --market-price-col E \
  --pct-change-col F

# Daemon mode with auto-trigger earnings script on new tickers
python update_extended_hours_prices.py \
  --spreadsheet-id YOUR_SHEET_ID \
  --tab-name "Prices" \
  --row 2 --col D \
  --ticker-col A \
  --daemon --interval 10 \
  --on-new-tickers-cmd "cd tradingview_scraper && python run_earnings_to_sheets.py \
    --tickers-file ../tickers_from_spreadsheet.txt \
    --spreadsheet-id YOUR_SHEET_ID \
    --date {date} --tab-name Earnings_Data"
```

**Available Columns:**
| Option | Header | Description |
|--------|--------|-------------|
| `--col` | Extended Hour Price | Pre/post market price (required) |
| `--ticker-col` | Ticker | Stock symbol |
| `--prev-close-col` | Previous Close Price | Yesterday's close |
| `--close-col` | Close Price | Today's close (N/A if market open) |
| `--market-price-col` | Market Price(with extended hour) | Best available current price |
| `--pct-change-col` | % Change Since Last Close | % change from previous close |
| `--diff-col` | Percentage Change | % change from regular market price |

### Earnings Analysis

See `tradingview_scraper/README.md` for earnings analysis tools.

## Project Structure
```
financial_analysis_agent/
├── data/                   # Data storage
├── financial_analysis_agent/
│   ├── __init__.py
│   ├── config.py           # Configuration management
│   ├── financial/          # Financial data modules
│   ├── social/             # Social media modules
│   ├── llm/                # LLM integration
│   └── analysis/           # Analysis and visualization
├── tests/                  # Unit tests
├── .env.example            # Example environment variables
├── requirements.txt        # Project dependencies
└── README.md               # This file
```
