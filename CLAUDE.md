# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Financial Analysis Agent is a Python tool that combines financial data analysis with social media sentiment analysis using LLMs. The project aims to:
1. Collect and analyze company fundamentals, stock prices, social media data, and news
2. Provide a learning platform for LLM, NLP, and fine-tuning concepts

## Development Commands

### Environment Setup
```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Set up environment variables
cp .env.example .env
# Edit .env with required API keys
```

### Running Analysis
```bash
# Full analysis (financial + social + LLM summary)
python -m financial_analysis_agent.analyze AAPL --analysis-type full --verbose

# Financial analysis only (no social/LLM), with JSON output
python -m financial_analysis_agent.analyze AAPL --analysis-type financial --verbose --output aapl.json

# Use quarterly instead of annual financial statements
python -m financial_analysis_agent.analyze AAPL --analysis-type financial --financial-period quarterly
```

### Code Quality
```bash
# Linting (used in CI)
pylint $(git ls-files '*.py')

# Formatting
black .
isort .

# Type checking
mypy financial_analysis_agent

# Testing
pytest
pytest --cov=financial_analysis_agent
```

## Architecture

### Multi-Source Data Fetcher Pattern

The `FinancialDataFetcher` class (financial_analysis_agent/financial/data_fetcher.py:16) is the central data access layer that intelligently selects from multiple financial data sources:

- **Source Priority**: For analyst estimates, it tries FMP → Finnhub → YahooQuery → yfinance in order
- **Source Instances**: Lazily initialized via properties (alpha_vantage_source:49, finnhub_source:56, fmp_source:63)
- **Data Sources Module**: All sources in `financial_analysis_agent/financial/sources/` implement a common pattern:
  - `yfinance_source.py`: Free stock data, company info, financials, earnings dates
  - `yahooquery_source.py`: Alternative free source with analyst estimates (forward-looking only)
  - `finnhub_source.py`: Premium API for analyst EPS estimates (revenue requires paid tier)
  - `fmp_source.py`: Financial Modeling Prep API for comprehensive EPS & revenue estimates (both historical and forward)
  - `alpha_vantage_source.py`: Alternative stock price data source

### Analysis Flow

The main analysis pipeline in `analyze.py`:

1. **FinancialAnalysisAgent** (analyze.py:74) orchestrates all analysis
2. **_analyze_financials** (analyze.py:166) fetches data via `FinancialDataFetcher`, calculates ratios with `CompanyFundamentals`, and technical indicators with `MarketData`
3. **_build_analyst_estimates** (analyze.py:231) merges EPS and revenue estimates from multiple sources
4. **_analyze_social_media** (analyze.py:376) collects Twitter and Reddit sentiment
5. **_analyze_sentiment** (analyze.py:476) uses LLM for deeper sentiment analysis
6. **_generate_summary** (analyze.py:606) creates final LLM-powered report

### JSON Serialization

The `_to_jsonable` function (analyze.py:16) recursively converts numpy/pandas objects to JSON-serializable types. Use this pattern when adding new data structures that may contain numpy arrays, pandas DataFrames, or Timestamps.

### Configuration Management

- **Singleton Pattern**: `Config` class (config.py:11) uses singleton pattern for app-wide settings
- **Environment Variables**: All API keys and paths loaded from `.env` via python-dotenv
- **Required API Keys** (config.py:48-80):
  - `ALPHA_VANTAGE_API_KEY` (optional)
  - `OPENAI_API_KEY` (required for LLM features)
  - `TWITTER_API_KEY`, `TWITTER_API_SECRET`, etc. (optional for social analysis)
  - `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, etc. (optional for social analysis)
  - `FMP_API_KEY` (optional, **recommended** - provides both historical & forward EPS/revenue estimates)
  - `FINNHUB_API_KEY` (optional, provides EPS estimates, revenue requires paid tier)

### Module Structure

```
financial_analysis_agent/
├── analyze.py              # Main FinancialAnalysisAgent class and CLI entry point
├── config.py               # Singleton configuration manager
├── financial/              # Financial data layer
│   ├── data_fetcher.py     # Multi-source data access orchestrator
│   ├── fundamentals.py     # Financial ratio calculations and health scoring
│   ├── market_data.py      # Technical indicators, volatility, support/resistance
│   ├── sources/            # Individual data source implementations
│   └── utils/              # Date utilities, DataFrame helpers, estimate merging
├── social/                 # Social media sentiment analysis
│   ├── twitter_client.py   # Twitter API integration
│   ├── reddit_client.py    # Reddit API integration
│   └── sentiment_analyzer.py
├── llm/                    # LLM integration layer
│   ├── base.py             # Base LLM client interface
│   ├── openai_client.py    # OpenAI GPT integration
│   └── hf_client.py        # HuggingFace models integration
└── storage/                # Data persistence (DuckDB)
    ├── engine.py
    └── repositories.py
```

## Docker

A lightweight Docker image is available for running the quarterly earnings price tracker without installing the full ML dependencies.

### Build the Image
```bash
docker build -t financial-tracker .
```

### Configuration

1. Create `.env.docker` from `.env.example` and set:
   ```
   GOOGLE_SHEETS_CREDENTIALS_PATH=/app/credentials/creds.json
   SPREADSHEET_ID=your_spreadsheet_id_here
   ```

2. The following environment variables can be configured (with defaults):
   - `SPREADSHEET_ID` - Google Sheets spreadsheet ID
   - `INTERVAL` - Update interval in seconds (default: 30)
   - `TAB_NAME` - Sheet tab name (default: LivePrices)
   - `FETCHED_EARNING_DATA_TAB_NAME` - Earnings data tab (default: Earnings_Data)

### Run the Price Tracker Daemon
```bash
# Remove any existing container and start fresh
docker rm -f tracker 2>/dev/null

# Run the daemon
docker run -d --name tracker \
  --env-file .env.docker \
  -v $(pwd)/.env.docker:/app/.env:ro \
  -v $(pwd)/your-google-credentials.json:/app/credentials/creds.json:ro \
  -v $(pwd)/data:/app/data \
  financial-tracker \
  bash -c "./quarterly_earnings_price_tracker.sh start && tail -f quarterly_earnings_price_tracker.log"
```

### Run Interactively
```bash
docker run -it --rm \
  --env-file .env.docker \
  -v $(pwd)/.env.docker:/app/.env:ro \
  -v $(pwd)/your-google-credentials.json:/app/credentials/creds.json:ro \
  -v $(pwd)/data:/app/data \
  financial-tracker bash
```

### View Logs
```bash
docker logs -f tracker
```

### Stop the Daemon
```bash
docker stop tracker
```

### One-time Price Update (without daemon)
```bash
docker run --rm \
  --env-file .env.docker \
  -v $(pwd)/.env.docker:/app/.env:ro \
  -v $(pwd)/your-google-credentials.json:/app/credentials/creds.json:ro \
  financial-tracker \
  python update_extended_hours_prices.py \
    --tickers "AAPL,MSFT,GOOGL" \
    --spreadsheet-id YOUR_SPREADSHEET_ID \
    --tab-name "LivePrices" \
    --row 2 --col D \
    --ticker-col A \
    --prev-close-col B \
    --close-col C \
    --market-price-col E \
    --pct-change-col F \
    --include-headers
```

## Code Style

- **Line Endings**: Always use Linux-style line endings (LF), not Windows-style (CRLF)
- To convert files: `sed -i '' 's/\r$//' <files>` (macOS) or `sed -i 's/\r$//' <files>` (Linux)

## Key Design Patterns

1. **Source Abstraction**: Each data source in `sources/` follows a consistent interface
2. **Lazy Initialization**: Expensive clients (Finnhub, Alpha Vantage) only initialized when needed
3. **Graceful Degradation**: Missing API keys or failed sources don't crash the app; warnings logged
4. **Analysis Types**: Use `--analysis-type` flag to run only needed components (financial/social/sentiment/full)

## Python Version

The project targets Python 3.11 (see .github/workflows/pylint.yml:10).

## Testing

No tests currently exist (tests/ directory is empty). When adding tests:
- Use pytest framework (included in requirements.txt)
- Test data fetcher source selection logic
- Mock external API calls to avoid rate limits
- Test JSON serialization of edge cases (NaN, inf, nested DataFrames)
