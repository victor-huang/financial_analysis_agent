# New Earnings Analysis Tool - Files Created

## Summary

Created a modular earnings analysis system that combines TradingView API and scraper data to generate comprehensive CSV reports.

## Files Created (5 new files)

### 1. `generate_earnings_analysis.py` (Main Script)
**Purpose**: Orchestrates the entire earnings analysis workflow

**Key Functions**:
- `generate_earnings_analysis()` - Main orchestration
- `main()` - CLI interface with argument parsing

**Usage**:
```bash
python generate_earnings_analysis.py --limit 3
```

### 2. `earnings_api_helper.py`
**Purpose**: Fetches earnings calendar data from TradingView API

**Key Functions**:
- `fetch_earnings_from_api()` - Calls TradingView scanner API
- `parse_api_response()` - Extracts ticker, company name, market cap, estimates
- `get_earnings_for_date()` - High-level function to get earnings for a date

**Returns**: Company name, market cap, sector, EPS/revenue estimates and actuals

### 3. `financial_data_helper.py`
**Purpose**: Scrapes historical financial data for YoY comparisons

**Key Functions**:
- `FinancialDataFetcher` class - Wraps the scraper
- `get_yoy_data()` - Gets current quarter vs same quarter last year
- `get_quarterly_eps_history()` - Gets all quarterly EPS data
- `get_quarterly_revenue_history()` - Gets all quarterly revenue data

**Returns**: Historical EPS and revenue for YoY calculations

### 4. `metrics_calculator.py`
**Purpose**: Calculates derived metrics and formats values

**Key Functions**:
- `calculate_beat_percentage()` - (Actual - Estimate) / Estimate × 100
- `calculate_yoy_percentage()` - (Current - LastYear) / LastYear × 100
- `format_market_cap()` - Formats market cap in billions
- `format_revenue()` - Formats revenue with B suffix
- `format_percentage()` - Formats percentages with % symbol

### 5. `csv_generator.py`
**Purpose**: Builds CSV rows and exports to file

**Key Functions**:
- `get_csv_headers()` - Returns list of 22 column headers
- `build_csv_row()` - Combines API data + YoY data into one row
- `save_to_csv()` - Writes data to CSV file

## Data Flow

```
┌─────────────────────────────────────────────────────────────┐
│                  generate_earnings_analysis.py              │
│                         (Main Script)                        │
└──────────────┬──────────────────────────┬───────────────────┘
               │                          │
               ▼                          ▼
    ┌──────────────────┐       ┌─────────────────────┐
    │ earnings_api     │       │ financial_data      │
    │ _helper.py       │       │ _helper.py          │
    │                  │       │                     │
    │ • Get earnings   │       │ • Scrape historical │
    │   calendar       │       │ • Calculate YoY     │
    │ • Current Q data │       │ • Get last year Q   │
    └──────────┬───────┘       └──────────┬──────────┘
               │                          │
               └──────────┬───────────────┘
                          ▼
                ┌──────────────────┐
                │ metrics_         │
                │ calculator.py    │
                │                  │
                │ • Beat %         │
                │ • YoY %          │
                │ • Formatting     │
                └─────────┬────────┘
                          │
                          ▼
                ┌──────────────────┐
                │ csv_generator.py │
                │                  │
                │ • Build rows     │
                │ • Export CSV     │
                └──────────────────┘
                          │
                          ▼
                earnings_analysis_2026-01-10.csv
```

## CSV Output Structure (22 Columns)

### From API (earnings_api_helper.py)
1. ticker
2. Company name
3. Market segment
4. Market Cap (B)
5. EPS Q estimate
6. EPS Q actual
7. Revenue Q estimate
8. revenue Q actual

### From Scraper (financial_data_helper.py)
9. EPS Q last year
10. Revenue Q last year
11. Revenue last Q

### Calculated (metrics_calculator.py)
12. EPS beat %
13. Revenue Q Beat %
14. EPS YoY %
15. Revenue YoY %
16. Revenue last Q YoY %

### Manual Input Fields (empty, user fills in)
17. hot?
18. Note
19. Fast grow?
20. tech/analyst

### Not Available Yet
21. HC change (%)
22. post gain $
23. 2nd day gain %

## Quick Start

```bash
cd tradingview_scraper

# Test with 3 tickers
python generate_earnings_analysis.py --limit 3

# Generate for today
python generate_earnings_analysis.py

# Generate for specific date
python generate_earnings_analysis.py --date 2025-01-15
```

## Dependencies

All modules import from each other:
- `generate_earnings_analysis.py` imports all 3 helpers
- `csv_generator.py` imports `metrics_calculator`
- `financial_data_helper.py` imports `tradingview_final_scraper`

## Testing Recommendation

1. **First test**: `python generate_earnings_analysis.py --limit 1`
2. **Small test**: `python generate_earnings_analysis.py --limit 3`
3. **Full run**: `python generate_earnings_analysis.py`

## Design Benefits

✅ **Modular**: Each file has a single responsibility
✅ **Testable**: Each helper can be tested independently
✅ **Maintainable**: Easy to update one component without affecting others
✅ **Reusable**: Helpers can be imported by other scripts
✅ **Readable**: Clear separation of concerns

## Example Usage in Code

```python
# Use individual helpers in your own scripts
from earnings_api_helper import get_earnings_for_date
from financial_data_helper import FinancialDataFetcher
from metrics_calculator import calculate_yoy_percentage

# Get earnings for today
earnings = get_earnings_for_date(datetime.now())

# Get YoY data for a specific ticker
fetcher = FinancialDataFetcher()
yoy_data = fetcher.get_yoy_data("AAPL", "NASDAQ")

# Calculate YoY growth
yoy_pct = calculate_yoy_percentage(100, 80)  # 25%
```
