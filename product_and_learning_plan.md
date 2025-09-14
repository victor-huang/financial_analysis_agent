# Financial Analysis Agent: Product and Learning Plan

## Objectives
- Build a financial analysis product that fuses company fundamentals, earnings call transcripts, social sentiment, and market data to produce explainable rankings and analyst-style insights.
- Learn and apply modern LLM techniques (RAG, tool use, QLoRA SFT, DPO) with strong evaluation for numeric correctness and faithfulness.

## System Overview
- Data sources
  - Fundamentals and prices: Yahoo Finance, Alpha Vantage (optionally SEC EDGAR).
  - Transcripts: file-drop ingestion initially; later scraped or API.
  - Social: Reddit and Twitter clients with FinBERT/VADER sentiment.
  - News: `yfinance.Ticker.news` as a baseline.
- Storage
  - Recommend DuckDB (file-based columnar analytics). Optional Google Sheets export.
- Processing
  - Feature engineering for growth, margins, market momentum, transcript tone, and social momentum.
- LLM layer
  - RAG over filings/transcripts/social summaries with citations.
  - Tool use for SQL/aggregation to compute numeric answers with “show your work”.
- Output
  - Ranking reports (overall and per sector), evidence-grounded Q&A, Sheets/CSV exports.

## Minimal Data Schema (DuckDB suggested)
- `companies(ticker, name, sector, industry, market_cap, country)`
- `prices(ticker, date, open, high, low, close, volume)`
- `fundamentals(ticker, period_end, period_type, revenue, gross_profit, opex, operating_income, net_income, assets, liabilities, equity, ocf, capex)`
- `transcripts(ticker, event_date, speaker, role, text, source)`
- `social_agg(ticker, date, platform, mentions, avg_sentiment, pos_count, neg_count, neu_count)`
- `news(ticker, published_at, publisher, title, link, sentiment)`
- `rankings(run_id, asof_date, ticker, score, rank, component_breakdown_json)`

## Roadmap Stages
1. Storage and Repos
   - Implement DuckDB engine, migrations, and repository classes per table.
   - Optional Sheets exporter for user-facing sharing.
2. Ingestion Pipelines
   - Prices and yfinance fundamentals (baseline).
   - News via yfinance; SEC EDGAR (optional, later).
   - Transcripts via file-drop directory.
   - Social clients aggregate daily metrics into `social_agg`.
3. Feature Engineering
   - Growth: YoY/QoQ revenue and net income.
   - Profitability: gross/operating/net margins; trends.
   - Cash and leverage: FCF, FCF margin, D/E.
   - Market: momentum (1M/3M/6M), vol, drawdown, 52w high distance.
   - Transcripts: aspect-based tone (guidance, demand, margins, macro).
   - Social: mention delta (7D vs 30D), sentiment ratio, engagement.
4. Ranking Engine
   - YAML-configurable weights and formulas.
   - Produce overall and sector top-N; export breakdown components.
5. RAG + Tool Use (Evidence-Grounded)
   - Index: filings (parsed), transcripts, social/news summaries.
   - Retrieval: BM25 + dense embeddings + reranker.
   - SQL calculator tool for numeric answers; enforce citations and formulas.
6. Evaluation and Backtesting
   - Numeric correctness (tolerances), faithfulness (attribution%), style.
   - Ranking backtest around earnings over a small ticker universe.
7. Domain Adaptation (Optional)
   - SFT 5–10k Q/A with citations (from your data).
   - QLoRA fine-tune a small open model; DPO to prefer concise, cited, numeric answers.

## Six-Week Plan
- Week 1: Storage + Minimum Ingestion
  - DuckDB engine and repositories. Ingest 3–5 tickers (3 years): prices, yfinance fundamentals, news.
  - Daily social aggregation (Reddit/Twitter) into `social_agg` table.
- Week 2: Transcripts + Features
  - File-drop transcripts; implement aspect sentiment. Compute growth/margins/FCF/leverage/market/social features.
- Week 3: Ranking Engine
  - YAML weights; output top-N with component breakdown. Export CSV/Sheets.
- Week 4: RAG with Citations
  - Chunk filings/transcripts; build hybrid retriever; add SQL calculator tool; format “show your work”.
- Week 5: Evaluation Harness
  - Golden numeric Q&A; faithfulness scoring; ranking backtest for selected tickers.
- Week 6: SFT + DPO (Optional)
  - Curate 5–10k examples; QLoRA fine-tune; small DPO dataset to bias toward concise cited answers.

## Evaluation
- Numeric accuracy: absolute/relative tolerance on derived metrics.
- Faithfulness: percent of claims with valid citations to indexed sources.
- Ranking: top-k precision/hit-rate, sector-wise score stability.
- Latency and cost: retrieval + generation time, API usage.

## LLM Recipes
- RAG
  - Chunk size 512–800 tokens; overlap 50–100.
  - Metadata: ticker, period_end, section, source.
  - Rerank top-100 BM25 to top-10 with embeddings; re-score with cross-encoder (optional).
- Tool Use
  - SQL calculator to fetch rows from DuckDB; all numbers referenced in the final answer must be pulled via SQL and displayed alongside formulas.
- Training (Optional)
  - QLoRA fine-tune on your SFT set. Use evaluation harness to track gains.
  - DPO pairwise preferences: concise, numeric-first, well-cited answers.

## Immediate Next Actions
- Confirm storage choice: DuckDB (recommended).
- Choose initial 3–5 tickers and time horizon (e.g., 3–5 years).
- I’ll scaffold storage, ingestion, features, and a first ranking report CLI.

## CLI Examples
```bash
# Full report (financial + social + LLM summary)
python -m financial_analysis_agent.analyze AAPL --analysis-type full --verbose

# Financial-only with output
python -m financial_analysis_agent.analyze AAPL --analysis-type financial --verbose --output aapl.json
```
