# TradingView API Research Summary

**Research Date:** 2026-01-10
**Objective:** Determine if TradingView provides historical annual revenue/EPS data and year-over-year quarterly comparisons

---

## Key Findings

### ✅ What TradingView Scanner API DOES Provide

The TradingView Scanner API (`https://scanner.tradingview.com/america/scan`) provides:

#### Current Fiscal Year (FY) Data:
- `earnings_per_share_fy` - Annual EPS for current fiscal year (e.g., 8.29 for MU)
- `earnings_per_share_diluted_fy` - Diluted annual EPS (e.g., 7.5902)
- `earnings_per_share_basic_fy` - Basic annual EPS (e.g., 7.6514)
- `total_revenue` - Total annual revenue (e.g., $37.378B for MU)
- `net_income` / `net_income_fy` - Annual net income (e.g., $8.539B)

#### Current Quarter (FQ) Data:
- `earnings_per_share_fq` - Reported EPS for most recent quarter
- `revenue_fq` - Reported revenue for most recent quarter
- `earnings_per_share_diluted_fq` - Diluted quarterly EPS
- `earnings_per_share_basic_fq` - Basic quarterly EPS

#### Trailing Twelve Months (TTM):
- `total_revenue_ttm` - Revenue for past 12 months (e.g., $42.312B for MU)

#### Forecast Data:
- `earnings_per_share_forecast_fq` - EPS estimate for current/upcoming quarter
- `revenue_forecast_fq` - Revenue estimate for current/upcoming quarter
- `earnings_per_share_forecast_next_fq` - Next quarter EPS estimate
- `revenue_forecast_next_fq` - Next quarter revenue estimate

#### Earnings Surprise:
- `eps_surprise_fq` - Difference between actual and estimated
- `eps_surprise_percent_fq` - Percentage surprise

---

### ❌ What TradingView Scanner API DOES NOT Provide

**Tested 28+ field variations - ALL FAILED:**

#### Multi-Year Historical Data:
- ❌ No previous fiscal years (FY-1, FY-2, FY-3, FY-4, FY-5)
- ❌ No historical annual revenue/EPS series
- ❌ No 5-year revenue/earnings history

#### Year-over-Year Comparisons:
- ❌ No same quarter last year data
- ❌ No YoY growth rates
- ❌ No quarter-to-quarter comparisons

#### Historical Quarterly Data:
- ❌ No previous quarter data (FQ-1, FQ-2, etc.)
- ❌ No quarterly history series

**Tested field patterns included:**
```
earnings_per_share_fy_1, earnings_per_share_fy_2, ..., earnings_per_share_fy_5
earnings_per_share_prev_fy, total_revenue_prev_fy
earnings_per_share_fq1, earnings_per_share_fq2, ..., earnings_per_share_fq4
earnings_per_share_yoy_growth_fq, revenue_yoy_growth_fq
earnings_per_share_sq (same quarter)
... and many more variations
```

---

## Alternative Data Sources

### Your Existing yfinance Source (RECOMMENDED)

The `YFinanceSource` class (yfinance_source.py:132) **ALREADY PROVIDES** what you need:

#### 1. Multi-Year Historical Financials
```python
# Get annual income statements for past 5 years
source.get_financials(ticker="MU", statement_type="income", period="annual", limit=5)

# Returns DataFrame with columns:
# - Total Revenue
# - Net Income
# - Basic EPS
# - Diluted EPS
# ... for each of the past 5 fiscal years
```

#### 2. Quarterly Historical Data
```python
# Get quarterly income statements (can get same quarter last year)
source.get_financials(ticker="MU", statement_type="income", period="quarterly", limit=8)

# Returns last 8 quarters of data, allowing you to:
# - Compare Q3 2024 vs Q3 2023 (same quarter YoY)
# - Calculate YoY growth rates
# - Track quarterly trends
```

#### 3. Earnings History with Surprises
```python
# Get earnings dates with actual vs estimated EPS
source.get_earnings_dates(ticker="MU", limit=8)

# Returns DataFrame with:
# - EPS Estimate
# - Reported EPS
# - Surprise amount
# - Surprise percentage
```

---

## Data Comparison

| Data Type | TradingView | yfinance | FMP | Recommendation |
|-----------|-------------|----------|-----|----------------|
| Current FY revenue/EPS | ✅ | ✅ | ✅ | Any source |
| Current FQ revenue/EPS | ✅ | ✅ | ✅ | Any source |
| Past 5 years annual data | ❌ | ✅ | ✅ | **Use yfinance or FMP** |
| Same quarter YoY | ❌ | ✅ | ✅ | **Use yfinance or FMP** |
| Historical quarters (8+) | ❌ | ✅ | ✅ | **Use yfinance or FMP** |
| Forward estimates | ✅ | ⚠️ Limited | ✅ | TradingView or FMP |
| Earnings surprise | ✅ | ✅ | ❌ | TradingView or yfinance |

---

## Recommendations

### For Your Use Case (Historical Annual + YoY Quarterly Data):

**USE EXISTING YFINANCE SOURCE** - No need to integrate TradingView for this requirement.

#### Implementation Example:

```python
from financial_analysis_agent.financial.sources.yfinance_source import YFinanceSource

source = YFinanceSource()

# Get past 5 years of annual data
annual_income = source.get_financials("MU", "income", "annual", limit=5)
revenue_5y = annual_income["Total Revenue"]
eps_5y = annual_income["Diluted EPS"]

# Get past 8 quarters (2 years) for YoY comparison
quarterly_income = source.get_financials("MU", "income", "quarterly", limit=8)

# Compare Q4 2024 vs Q4 2023 (quarters 0 and 4)
current_q = quarterly_income.iloc[0]
same_q_last_year = quarterly_income.iloc[4]

yoy_revenue_growth = (current_q["Total Revenue"] - same_q_last_year["Total Revenue"]) / same_q_last_year["Total Revenue"]
yoy_eps_growth = (current_q["Diluted EPS"] - same_q_last_year["Diluted EPS"]) / same_q_last_year["Diluted EPS"]
```

### When to Use TradingView:

TradingView is best for:
1. **Forward-looking estimates** - Next quarter/year forecasts
2. **Earnings calendar** - Upcoming earnings announcement dates
3. **Real-time surprises** - Immediate beat/miss data on earnings day
4. **Broad market screening** - Scan hundreds of tickers at once for earnings on specific dates

### When to Use yfinance:

Use yfinance for:
1. **Historical financial statements** - Multi-year annual/quarterly data ✅
2. **Year-over-year comparisons** - Same quarter last year ✅
3. **Earnings history** - Past EPS actuals vs estimates ✅
4. **Free tier usage** - No API key required ✅

---

## Conclusion

**TradingView Scanner API does NOT provide multi-year historical data or same-quarter year-over-year comparisons.**

**Your existing `YFinanceSource` already has everything you need** for:
- Past 5 years of annual revenue and EPS
- Same quarter last year comparisons
- Historical quarterly data

No additional integration required. Simply use the existing `get_financials()` method with appropriate parameters.

---

## Test Scripts Created

1. `test_tradingview_fields.py` - Test basic field availability
2. `test_tradingview_fields_individual.py` - Test each field individually (found 9 working annual/quarterly fields)
3. `test_tradingview_historical.py` - Test for historical year data (found 0 working historical fields)

All test scripts confirmed that TradingView only provides current period data, not historical series.
