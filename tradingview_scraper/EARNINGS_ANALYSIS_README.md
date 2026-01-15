# Earnings Analysis CSV Generator

This tool generates a comprehensive earnings analysis CSV by combining:
1. **TradingView Earnings API** - Current quarter estimates and actuals
2. **TradingView Scraper** - Historical data for YoY comparisons

## Files Structure

```
tradingview_scraper/
├── generate_earnings_analysis.py   # Main script (run this)
├── earnings_api_helper.py          # Fetches earnings calendar
├── financial_data_helper.py        # Scrapes historical financial data
├── metrics_calculator.py           # Calculates beat %, YoY %, etc.
├── csv_generator.py                # Builds and exports CSV
└── tradingview_final_scraper.py    # Core scraping engine
```

## Quick Start

### Basic Usage (Today's Earnings)

```bash
cd tradingview_scraper
python generate_earnings_analysis.py
```

This will:
1. Fetch today's earnings from TradingView API
2. Scrape detailed financial data for each ticker
3. Calculate YoY comparisons and beat percentages
4. Generate `earnings_analysis_2026-01-10.csv`

### Specific Date

```bash
python generate_earnings_analysis.py --date 2025-01-15
```

### Test with Limited Tickers (Recommended First Run)

```bash
python generate_earnings_analysis.py --limit 3
```

This will only process the first 3 tickers (useful for testing).

### Custom Output File

```bash
python generate_earnings_analysis.py --output my_analysis.csv
```

### Show Browser (For Debugging)

```bash
python generate_earnings_analysis.py --no-headless
```

## CSV Output Columns

| Column | Description | Source |
|--------|-------------|--------|
| ticker | Stock ticker symbol | API |
| hot? | Manual input field | - |
| Note | Manual input field | - |
| Company name | Company full name | API |
| Market segment | Sector/Industry | API |
| Market Cap (B) | Market cap in billions | API |
| Fast grow? | Manual input field | - |
| HC change (%) | Not available | - |
| tech/analyst | Manual input field | - |
| post gain $ | Post-earnings price movement | Not available yet |
| 2nd day gain % | 2nd day price movement | Not available yet |
| **EPS Q estimate** | Current quarter EPS estimate | API |
| **EPS Q actual** | Current quarter EPS actual | API |
| **EPS beat %** | Beat percentage | Calculated |
| **Revenue Q estimate** | Current quarter revenue estimate | API |
| **revenue Q actual** | Current quarter revenue actual | API |
| **Revenue Q Beat %** | Beat percentage | Calculated |
| **EPS Q last year** | Same quarter last year EPS | Scraper |
| **EPS YoY %** | Year-over-year growth | Calculated |
| **Revenue Q last year** | Same quarter last year revenue | Scraper |
| **Revenue YoY %** | Year-over-year growth | Calculated |
| **Revenue last Q YoY %** | Previous quarter YoY growth | Calculated |

## Requirements

```bash
pip install selenium beautifulsoup4 requests
```

## Performance Notes

- **Processing Time**: ~15-20 seconds per ticker
- **Example**: 20 tickers = ~6-7 minutes
- **Tip**: Use `--limit 5` for testing to process only first 5 tickers

## Common Use Cases

### Morning Routine - Get Today's Earnings

```bash
python generate_earnings_analysis.py --limit 10
```

### Analyze Yesterday's Results

```bash
python generate_earnings_analysis.py --date 2026-01-09
```

### Full Analysis (All Tickers)

```bash
python generate_earnings_analysis.py
```

## Troubleshooting

### Error: "No earnings found for this date"
- Check if there are actually earnings on that date
- Try a different date or today's date

### Scraper times out or fails
- Some tickers may not have TradingView forecast pages
- The script will continue processing other tickers
- Check error messages for specific failures

### Browser issues
- Make sure Chrome/Chromium is installed
- Try running with `--no-headless` to see what's happening
- Update Selenium: `pip install --upgrade selenium`

## Field Explanations

### Beat Percentage
```
EPS Beat % = ((Actual - Estimate) / Estimate) × 100
```
Example: Estimate $2.00, Actual $2.10 → Beat % = 5%

### YoY Percentage
```
YoY % = ((Current Quarter - Same Quarter Last Year) / Same Quarter Last Year) × 100
```
Example: Q1 2025 = $100M, Q1 2024 = $80M → YoY % = 25%

## Empty Fields

Some fields are intentionally left empty:
- **hot?, Note, Fast grow?, tech/analyst**: User input fields for manual analysis
- **HC change (%)**: Headcount data not available
- **post gain $, 2nd day gain %**: Would require post-earnings price tracking

## Example Output

```csv
ticker,hot?,Note,Company name,Market segment,Market Cap (B),...
AAPL,,,"Apple Inc.",Technology,2847.53,...
TSLA,,,"Tesla, Inc.",Consumer Cyclical,789.23,...
NVDA,,,"NVIDIA Corporation",Technology,1234.56,...
```

## Tips

1. **Test First**: Always run with `--limit 3` first to verify everything works
2. **Morning Run**: Run early to get ahead of market open
3. **Save Results**: Output files are timestamped, so you can compare across days
4. **Manual Fields**: Open the CSV in Excel/Sheets to fill in manual analysis fields

## Support

For issues or questions:
1. Check the error messages - they usually indicate what went wrong
2. Try with `--limit 1` to isolate the problem
3. Run with `--no-headless` to see browser behavior
4. Check that TradingView is accessible and not blocking requests
