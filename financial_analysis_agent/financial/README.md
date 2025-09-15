# Financial Data Module

This module provides functionality for retrieving and analyzing financial data from various sources.

## Architecture

The financial data module has been refactored into a modular architecture:

```
financial/
├── sources/                # Source-specific implementations
│   ├── __init__.py
│   ├── yfinance_source.py  # Yahoo Finance API
│   ├── alpha_vantage_source.py  # Alpha Vantage API
│   ├── finnhub_source.py   # Finnhub API
│   └── yahooquery_source.py  # YahooQuery API
├── utils/                  # Common utilities
│   ├── __init__.py
│   ├── date_utils.py       # Date parsing and manipulation
│   └── dataframe_utils.py  # DataFrame operations
├── __init__.py
├── data_fetcher.py         # Main interface (delegates to sources)
└── [other modules]
```

## Usage

The main interface is the `FinancialDataFetcher` class which delegates to source-specific implementations:

```python
from financial_analysis_agent.financial import FinancialDataFetcher

# Initialize with optional API keys
fetcher = FinancialDataFetcher()

# Get stock data
df = fetcher.get_stock_data('AAPL', start_date='2023-01-01', end_date='2023-12-31')

# Get analyst estimates (automatically selects best available source)
estimates = fetcher.get_analyst_estimates('AAPL')
```

## Migration from Legacy Structure

If you're migrating from the legacy monolithic structure:

1. Import from the same location: `from financial_analysis_agent.financial import FinancialDataFetcher`
2. The public API remains the same, so your existing code should work without changes
3. If you were directly accessing source-specific methods, you may need to update your code

## Source Priorities

For analyst estimates, the sources are tried in this order:
1. Finnhub (with revenue enrichment if needed)
2. YahooQuery
3. YFinance earnings trend

This prioritization can be customized by directly calling source-specific methods if needed.
