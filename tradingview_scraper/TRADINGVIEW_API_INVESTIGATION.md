# TradingView Forecast Page API Investigation

**Date:** 2026-01-10
**Objective:** Find the API endpoint that TradingView's forecast page uses to display historical revenue/EPS and forecast data

---

## Summary of Investigation

### What We've Discovered

1. **Scanner API is Limited**
   - The scanner API (`https://scanner.tradingview.com/america/scan`) only provides current period data
   - Does NOT provide historical multi-year data
   - Confirmed through extensive testing (28+ field variations tested)

2. **Forecast Page Uses Different Data Source**
   - The forecast page (`https://www.tradingview.com/symbols/NASDAQ-MU/forecast/`) displays historical data
   - This data is loaded AFTER the initial page load
   - Likely loaded via:
     - Dynamic JavaScript/AJAX calls
     - WebSocket connections
     - Embedded in JavaScript bundles

3. **Pages That Exist**
   - ✅ `https://www.tradingview.com/symbols/NASDAQ-MU/forecast/` (200 OK)
   - ✅ `https://www.tradingview.com/symbols/NASDAQ-MU/financials-overview/` (200 OK)
   - ✅ `https://www.tradingview.com/symbols/NASDAQ-MU/financials-statistics/` (might exist)

4. **Known TradingView Infrastructure**
   - WebSocket: `wss://data.tradingview.com`
   - Scanner: `https://scanner.tradingview.com`
   - Symbol Search: `https://symbol-search.tradingview.com`

---

## MANUAL API DISCOVERY STEPS

Since the data is loaded dynamically, you need to capture the actual network requests. Here's how:

### Step 1: Open Browser DevTools

1. Open Chrome or Firefox
2. Navigate to: `https://www.tradingview.com/symbols/NASDAQ-MU/forecast/`
3. Open Developer Tools:
   - Mac: `Cmd + Option + I`
   - Windows/Linux: `F12` or `Ctrl + Shift + I`

### Step 2: Monitor Network Traffic

1. Click on the **Network** tab
2. (Optional) Filter by **XHR** or **Fetch** to see only API calls
3. **Refresh the page** (`Cmd+R` or `Ctrl+R`)
4. Watch for requests being made as the page loads

### Step 3: Identify Financial Data Requests

Look for requests containing these keywords in the URL:
- `financial`
- `forecast`
- `revenue`
- `earnings`
- `estimates`
- `symbol`
- `quote`

Also check for:
- WebSocket connections (filter by **WS** tab)
- Requests to `*.tradingview.com` domains

### Step 4: Inspect the Request

When you find a promising request:

1. **Click on the request** in the Network tab
2. Check the **Headers** tab:
   - Request URL
   - Request Method (GET/POST)
   - Request Headers (especially authentication)
3. Check the **Payload** tab (if POST request):
   - What data is being sent?
   - What symbol/fields are requested?
4. Check the **Response** tab:
   - Does it contain historical revenue/EPS arrays?
   - What's the data structure?

### Step 5: Copy the Request

Right-click on the request and select:
- **Copy → Copy as cURL** (easiest to share)
- **Copy → Copy as fetch** (JavaScript format)

---

## What to Look For in the Response

The ideal API response should contain:

```json
{
  "symbol": "NASDAQ:MU",
  "financials": {
    "annual": {
      "revenue": [
        {"year": 2024, "value": 30000000000},
        {"year": 2023, "value": 27000000000},
        {"year": 2022, "value": 28000000000},
        {"year": 2021, "value": 26000000000},
        {"year": 2020, "value": 21000000000}
      ],
      "eps": [
        {"year": 2024, "value": 8.29},
        {"year": 2023, "value": 1.71},
        ...
      ]
    },
    "quarterly": {
      "revenue": [...],
      "eps": [...]
    }
  },
  "estimates": {
    "revenue": [...],
    "eps": [...]
  }
}
```

---

## Common TradingView API Patterns

Based on other financial sites and TradingView's infrastructure, try these patterns:

### Pattern 1: REST API Endpoint
```
GET https://scanner.tradingview.com/symbol-financials?symbol=NASDAQ:MU
GET https://api.tradingview.com/v1/symbols/NASDAQ:MU/financials
GET https://symbol-data.tradingview.com/financials/NASDAQ:MU
```

### Pattern 2: WebSocket Protocol
```javascript
// Connect to WebSocket
wss://data.tradingview.com/socket.io/?...

// Send message requesting financial data
{
  "m": "symbol_financials",
  "p": ["NASDAQ:MU", "annual,quarterly"]
}
```

### Pattern 3: GraphQL API
```
POST https://api.tradingview.com/graphql

{
  query: {
    symbol(symbol: "NASDAQ:MU") {
      financials {
        annual { revenue, eps }
        quarterly { revenue, eps }
      }
    }
  }
}
```

---

## Alternative: Browser Automation

If manual inspection is too complex, we can use browser automation:

### Option 1: Install Selenium
```bash
pip install selenium webdriver-manager
python capture_tradingview_requests.py
```

### Option 2: Install Playwright
```bash
pip install playwright
playwright install
# Then modify capture script to use playwright
```

These tools will:
- Load the actual page in a headless browser
- Capture all network requests
- Show us the exact API endpoints used

---

## Next Steps

### Option A: Manual Discovery (Recommended First)
1. Follow the manual steps above to capture the API request
2. Share the cURL command or request details
3. We'll create a Python script to replicate the request

### Option B: Browser Automation
1. Install Selenium: `pip install selenium webdriver-manager`
2. Run: `python capture_tradingview_requests.py`
3. Review captured API calls

### Option C: Reverse Engineer JavaScript
1. Find the JavaScript bundle that loads the financial data
2. Search for API endpoint strings in the code
3. Understand the authentication/session requirements

---

## Scripts Created

1. **test_tradingview_fields_individual.py**
   Tests Scanner API fields - confirmed it lacks historical data

2. **inspect_tradingview_forecast_api.py**
   Tests various potential API endpoint patterns

3. **extract_tradingview_financials.py**
   Attempts to extract embedded data from HTML

4. **capture_tradingview_requests.py**
   Browser automation script (requires Selenium/Playwright)

---

## Important Notes

- TradingView may use anti-bot protection
- Some endpoints might require authentication
- Rate limiting may apply
- The API structure might change without notice
- Consider TradingView's Terms of Service regarding data scraping

---

## Once We Find the API

After discovering the correct API endpoint, we can:

1. Create a `TradingViewForecastSource` class
2. Integrate it into your `FinancialDataFetcher`
3. Use it as a primary source for historical + forecast data
4. Cache responses to minimize API calls

Example integration:
```python
from financial_analysis_agent.financial.sources.tradingview_forecast_source import TradingViewForecastSource

source = TradingViewForecastSource()

# Get 5 years of annual data + forecasts
data = source.get_financials_with_forecast(
    ticker="MU",
    exchange="NASDAQ",
    annual_years=5,
    quarterly_periods=8
)
```

---

## Questions?

Once you capture the network request, we can:
- Reverse engineer the request format
- Create a robust Python client
- Handle authentication if needed
- Implement error handling and retries
