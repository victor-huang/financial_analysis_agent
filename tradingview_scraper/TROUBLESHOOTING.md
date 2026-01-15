# Troubleshooting Guide

## Issue: Missing Revenue Data in Output

### Problem
When running the earnings analysis tool, some tickers show missing revenue YoY data in the output CSV.

### Root Cause
**Small-cap stocks often don't have forecast pages on TradingView.**

The system combines two data sources:
1. **TradingView Earnings API** - Provides current quarter estimates/actuals
2. **TradingView Forecast Pages (via scraper)** - Provides historical data for YoY comparisons

Small-cap stocks (typically under $1B market cap) may not have:
- Analyst coverage
- Forecast pages on TradingView
- Historical financial data in the required format

### Example
```bash
$ python generate_earnings_analysis.py --date 2026-01-09
```

Output shows:
```
⚠  Warning: 3 ticker(s) missing historical data:
   - AXG (no forecast data)
   - CYDY (no forecast data)
   - HURC (no forecast data)

Note: Small-cap stocks often lack TradingView forecast pages.
      Only API data (current estimates/actuals) is available for these.
```

### What Works vs. What Doesn't

#### ✅ Works - Large-cap stocks with analyst coverage
Examples: AAPL, MSFT, GOOGL, NVDA, MU, TSLA

These stocks have:
- Full forecast pages on TradingView
- Historical quarterly and annual data
- All YoY calculations available

#### ❌ Limited Data - Small-cap stocks
Examples: AXG ($0.81B), CYDY ($0.35B), HURC ($0.11B)

These stocks may have:
- Current quarter estimates from API (if available)
- Missing historical data
- Empty YoY fields in CSV

### Solution

**Option 1: Filter by market cap**
Only process companies above a certain market cap threshold:

```python
# In your code, filter the API results:
large_cap_companies = [
    company for company in api_data
    if company.get('market_cap', 0) > 1_000_000_000  # $1B+
]
```

**Option 2: Accept incomplete data**
The tool will still generate rows for these companies with:
- API data (current quarter estimates/actuals if available)
- Empty YoY fields
- This allows manual research/filling of data later

**Option 3: Use different dates**
Earnings dates with more large-cap companies will have better data coverage.

### Verification

Test with a known working ticker:
```bash
python -c "
from financial_data_helper import FinancialDataFetcher

fetcher = FinancialDataFetcher(headless=True)
try:
    yoy_data = fetcher.get_yoy_data('MU', 'NASDAQ')
    if yoy_data:
        print('✓ System working - found data for MU')
        print(f'  EPS current: {yoy_data.get(\"eps_current_q\")}')
        print(f'  Revenue current: {yoy_data.get(\"revenue_current_q\")} millions')
    else:
        print('✗ Issue with scraper')
finally:
    fetcher.close()
"
```

Expected output:
```
✓ System working - found data for MU
  EPS current: 4.78
  Revenue current: 13640.0 millions
```

### Data Quality Notes

1. **API Data Quality**: The TradingView API may return estimates/actuals even for small caps, but quality varies
2. **Scraper Requirements**: Requires forecast page to exist with charts/tables
3. **Historical Data**: Only available for stocks with analyst coverage

### Improved in Latest Version

- ✅ Better error detection for missing forecast pages
- ✅ Clear warnings about which tickers lack data
- ✅ Summary at end showing all skipped tickers
- ✅ Fixed revenue unit conversion bug (API uses dollars, scraper uses millions)
