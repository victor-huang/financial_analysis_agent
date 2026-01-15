# TradingView Scraper

This folder contains the TradingView data scraper that extracts EPS and Revenue data from TradingView forecast pages.

## Main File

**`tradingview_final_scraper.py`** - The complete working scraper

## Quick Start

```bash
cd tradingview_scraper
python tradingview_final_scraper.py
```

This will scrape data for Micron (MU) and save to `tradingview_MU_final.json`.

## Usage in Your Code

```python
import sys
sys.path.append('tradingview_scraper')
from tradingview_final_scraper import TradingViewFinalScraper

scraper = TradingViewFinalScraper(headless=True)
data = scraper.fetch_all_financial_data("AAPL", "NASDAQ")

# Access data
print(data["annual"]["eps"]["historical"])
print(data["annual"]["revenue"]["historical"])
```

## Requirements

```bash
pip install selenium beautifulsoup4
```

## What It Extracts

- ✅ Annual EPS (5+ years historical + forward estimates)
- ✅ Annual Revenue (5+ years historical + forward estimates)
- ✅ Quarterly EPS (7+ quarters historical + forward estimates)
- ✅ Quarterly Revenue (5+ quarters historical + forward estimates)

## Documentation

- `TRADINGVIEW_SCRAPER_SUCCESS.md` - Success summary
- `README_TRADINGVIEW_SCRAPER.md` - Detailed documentation
- `TRADINGVIEW_EPS_SCRAPER_FINAL.md` - Final implementation notes

## Other Files

This folder contains various research scripts and test files created during development:
- `test_*.py` - Testing scripts
- `*_scraper.py` - Various scraper iterations
- `*.json` - Example output files
- `*.html` - Saved HTML for debugging
- `*.md` - Research and documentation notes
