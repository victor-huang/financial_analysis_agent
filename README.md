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
```bash
# Full report (financial + social + LLM summary)
python -m financial_analysis_agent.analyze AAPL --analysis-type full --verbose

# Financials only (no social or LLM), optionally save to file
python -m financial_analysis_agent.analyze AAPL --analysis-type financial --verbose --output aapl.json
```

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
