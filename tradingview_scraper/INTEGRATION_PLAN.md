# TradingView Scraper Integration Plan

## Overview

Integrate the `tradingview_scraper` module into the parent `FinancialDataFetcher` class to provide TradingView as an additional data source for EPS and Revenue estimates.

## Goals

1. Follow existing source abstraction pattern (`sources/*.py`)
2. Provide TradingView historical data as supplementary source
3. Maintain backward compatibility with existing API
4. Keep scraper as optional (don't break app if Selenium unavailable)

## Current Architecture

```
financial_analysis_agent/
├── financial/
│   ├── data_fetcher.py          # Main orchestrator
│   ├── sources/
│   │   ├── __init__.py
│   │   ├── yfinance_source.py   # Free, no API key
│   │   ├── yahooquery_source.py # Free, no API key
│   │   ├── finnhub_source.py    # Requires API key
│   │   ├── fmp_source.py        # Requires API key
│   │   └── alpha_vantage_source.py
│   └── utils/
│       └── ...

tradingview_scraper/              # Standalone module (current)
├── tradingview_final_scraper.py # Core scraper
├── earnings_api_helper.py       # Earnings calendar API
├── financial_data_helper.py     # Scraper wrapper
├── metrics_calculator.py
├── csv_generator.py
└── generate_earnings_analysis.py
```

## Proposed Integration

### Option A: Full Integration (Recommended)

Create a new source class and integrate into FinancialDataFetcher.

```
financial_analysis_agent/
├── financial/
│   ├── data_fetcher.py          # Add tradingview_source property
│   ├── sources/
│   │   ├── __init__.py          # Export TradingViewSource
│   │   ├── tradingview_source.py # NEW - wrapper class
│   │   └── ...
```

### Option B: Lightweight Integration

Keep scraper in `tradingview_scraper/` folder, add import path to data_fetcher.

### Option C: Standalone (Current State)

Keep as separate tool, don't integrate into main data fetcher.

## Recommended Approach: Option A

### File Changes Required

#### 1. Create `financial_analysis_agent/financial/sources/tradingview_source.py`

```python
"""TradingView data source module for scraping financial data."""

import logging
import sys
from pathlib import Path
from typing import Dict, Optional

import pandas as pd

logger = logging.getLogger(__name__)

# Flag to track if scraper is available
SCRAPER_AVAILABLE = False

try:
    # Add tradingview_scraper to path
    scraper_path = Path(__file__).parent.parent.parent.parent / "tradingview_scraper"
    if scraper_path.exists():
        sys.path.insert(0, str(scraper_path))
        from tradingview_final_scraper import TradingViewFinalScraper
        SCRAPER_AVAILABLE = True
except ImportError as e:
    logger.warning(f"TradingView scraper not available: {e}")


class TradingViewSource:
    """Class to fetch financial data from TradingView via web scraping."""

    def __init__(self, headless: bool = True):
        """Initialize the TradingView data source.

        Args:
            headless: Run browser in headless mode (default: True)
        """
        self.headless = headless
        self._scraper = None

    @property
    def scraper(self):
        """Lazy initialization of scraper."""
        if not SCRAPER_AVAILABLE:
            return None
        if self._scraper is None:
            self._scraper = TradingViewFinalScraper(headless=self.headless)
        return self._scraper

    def is_available(self) -> bool:
        """Check if TradingView scraper is available."""
        return SCRAPER_AVAILABLE

    def get_financial_data(self, ticker: str, exchange: str = "NASDAQ") -> Optional[Dict]:
        """Fetch EPS and Revenue data from TradingView forecast page.

        Args:
            ticker: Stock ticker symbol
            exchange: Exchange name (NASDAQ, NYSE, etc.)

        Returns:
            Dictionary with quarterly/annual EPS and Revenue data
        """
        if not self.scraper:
            logger.warning("TradingView scraper not available")
            return None

        try:
            return self.scraper.fetch_all_financial_data(ticker, exchange)
        except Exception as e:
            logger.error(f"TradingView scraping failed for {ticker}: {e}")
            return None

    def get_quarterly_estimates(self, ticker: str, exchange: str = "NASDAQ") -> Optional[pd.DataFrame]:
        """Get quarterly EPS and Revenue estimates in standard DataFrame format.

        Args:
            ticker: Stock ticker symbol
            exchange: Exchange name

        Returns:
            DataFrame with columns: ['period', 'endDate', 'epsEstimateAvg',
                                     'epsActual', 'revenueEstimateAvg', 'revenueActual']
        """
        data = self.get_financial_data(ticker, exchange)
        if not data:
            return None

        # Transform to standard DataFrame format
        # ... implementation details ...
        pass

    def close(self):
        """Close the browser driver."""
        if self._scraper and hasattr(self._scraper, 'driver'):
            try:
                self._scraper.driver.quit()
            except Exception:
                pass
```

#### 2. Update `financial_analysis_agent/financial/sources/__init__.py`

```python
from .yfinance_source import YFinanceSource
from .alpha_vantage_source import AlphaVantageSource
from .finnhub_source import FinnhubSource
from .yahooquery_source import YahooQuerySource
from .fmp_source import FMPSource
from .tradingview_source import TradingViewSource  # NEW

__all__ = [
    "YFinanceSource",
    "AlphaVantageSource",
    "FinnhubSource",
    "YahooQuerySource",
    "FMPSource",
    "TradingViewSource",  # NEW
]
```

#### 3. Update `financial_analysis_agent/financial/data_fetcher.py`

```python
# Add import
from .sources import (..., TradingViewSource)

class FinancialDataFetcher:
    def __init__(self, api_key: str = None):
        # ... existing init ...

        # TradingView setup (no API key needed, uses web scraping)
        self._tradingview_source = None

    @property
    def tradingview_source(self) -> Optional[TradingViewSource]:
        """Get or initialize the TradingView source (lazy, expensive)."""
        if self._tradingview_source is None:
            self._tradingview_source = TradingViewSource(headless=True)
        return self._tradingview_source

    def get_tradingview_estimates(
        self,
        ticker: str,
        exchange: str = "NASDAQ"
    ) -> Optional[Dict]:
        """Get historical EPS/Revenue from TradingView.

        Note: This is slow (~15-20s per ticker) due to web scraping.
        Use sparingly or for specific historical data needs.

        Args:
            ticker: Stock ticker symbol
            exchange: Exchange (NASDAQ, NYSE, AMEX, OTC)

        Returns:
            Dictionary with quarterly and annual EPS/Revenue data
        """
        if not self.tradingview_source.is_available():
            logger.warning("TradingView scraper not available (missing dependencies)")
            return None
        return self.tradingview_source.get_financial_data(ticker, exchange)

    def get_tradingview_quarterly_estimates(
        self,
        ticker: str,
        exchange: str = "NASDAQ"
    ) -> Optional[pd.DataFrame]:
        """Get quarterly estimates from TradingView in standard DataFrame format.

        Note: Slow operation. Consider caching results.
        """
        if not self.tradingview_source.is_available():
            return None
        return self.tradingview_source.get_quarterly_estimates(ticker, exchange)
```

## Integration Considerations

### Performance

| Source | Speed | Best For |
|--------|-------|----------|
| FMP API | <1s | Primary source |
| Finnhub API | <1s | EPS estimates |
| YahooQuery | 1-2s | Free fallback |
| yfinance | 1-2s | Basic data |
| **TradingView** | **15-20s** | **Historical charts, YoY data** |

**Recommendation**: Do NOT add TradingView to the `get_analyst_estimates()` priority chain. Keep it as a separate method for specific use cases.

### Dependencies

TradingView scraper requires:
- `selenium`
- `webdriver-manager` or ChromeDriver installed
- `beautifulsoup4`

These should be **optional dependencies**. The integration should gracefully degrade if unavailable.

```python
# In requirements.txt, add as optional:
# selenium>=4.0.0  # Optional: for TradingView scraper
# webdriver-manager>=4.0.0  # Optional: for TradingView scraper
```

### Data Coverage

TradingView forecast pages only exist for:
- Large-cap stocks with analyst coverage
- Stocks with market cap > ~$1B typically

Small-cap stocks will return `None`.

### Rate Limiting

- No explicit API rate limits (web scraping)
- Browser-based, so inherently slower
- Recommend adding delays between requests if batch processing

### DOM Stability

- TradingView can change their DOM structure at any time
- Scraper may break without notice
- Should have fallback handling and clear error messages

## Implementation Steps

### Phase 1: Create Source Class
1. Create `tradingview_source.py` with wrapper class
2. Implement `get_financial_data()` method
3. Implement `get_quarterly_estimates()` with DataFrame conversion
4. Add graceful degradation for missing dependencies
5. Update `sources/__init__.py`

### Phase 2: Integrate into DataFetcher
1. Add `_tradingview_source` attribute
2. Add `tradingview_source` property (lazy init)
3. Add `get_tradingview_estimates()` method
4. Add `get_tradingview_quarterly_estimates()` method
5. Add logging and error handling

### Phase 3: Testing
1. Unit tests for TradingViewSource class
2. Integration tests with FinancialDataFetcher
3. Test graceful degradation when Selenium unavailable
4. Test with various ticker types (large-cap, small-cap, OTC)

### Phase 4: Documentation
1. Update CLAUDE.md with new source
2. Add usage examples
3. Document limitations and best practices

## Usage Examples (After Integration)

```python
from financial_analysis_agent.financial.data_fetcher import FinancialDataFetcher

fetcher = FinancialDataFetcher()

# Quick API-based estimates (fast)
estimates = fetcher.get_analyst_estimates("AAPL")

# TradingView historical data (slow, but has YoY charts)
tv_data = fetcher.get_tradingview_estimates("AAPL", "NASDAQ")
if tv_data:
    quarterly_eps = tv_data["quarterly"]["eps"]["historical"]
    annual_revenue = tv_data["annual"]["revenue"]["historical"]

# Or as DataFrame for compatibility
tv_df = fetcher.get_tradingview_quarterly_estimates("AAPL")
```

## Decision: When to Use TradingView Source

| Use Case | Recommended Source |
|----------|-------------------|
| Quick analyst estimates | FMP/Finnhub/YahooQuery |
| Current quarter EPS/Revenue | Earnings API |
| Historical EPS trend (5+ years) | **TradingView** |
| YoY comparisons | **TradingView** |
| Batch processing (100+ tickers) | API sources |
| Single ticker deep dive | **TradingView** OK |

## Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| DOM structure changes | Versioned scraper, monitoring, quick fix process |
| Slow performance | Keep separate from main estimate chain, add caching |
| Selenium dependency issues | Graceful degradation, optional dependency |
| Rate limiting/blocking | Add delays, rotate user agents if needed |
| Small-cap data gaps | Clear error messages, document limitations |

## Timeline Estimate

| Phase | Effort |
|-------|--------|
| Phase 1: Source Class | 2-3 hours |
| Phase 2: DataFetcher Integration | 1-2 hours |
| Phase 3: Testing | 2-3 hours |
| Phase 4: Documentation | 1 hour |
| **Total** | **6-9 hours** |

## Open Questions

1. Should we add caching for TradingView results? (Redis, file-based, or in-memory)
2. Should TradingView be added to CI/CD tests? (Requires Chrome/Selenium in CI)
3. Should we create a separate "slow sources" category in the data fetcher?

---

**Status**: Planning Complete - Ready for Implementation

**Last Updated**: 2026-01-15
