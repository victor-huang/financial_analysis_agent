# Google Sheets Export Module

This module provides functionality to export CSV data to Google Sheets using the Google Sheets API.

## Features

- Write CSV files directly to Google Sheets
- Write data from Python lists to Google Sheets
- Append data to existing sheets
- Create new tabs automatically
- Format header rows (bold, background color)
- Clear existing data before writing
- Service account authentication

## Setup

### 1. Create Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select an existing one
3. Enable the Google Sheets API:
   - Navigate to "APIs & Services" > "Library"
   - Search for "Google Sheets API"
   - Click "Enable"

### 2. Create Service Account

1. Go to "APIs & Services" > "Credentials"
2. Click "Create Credentials" > "Service Account"
3. Fill in the service account details and click "Create"
4. Grant the service account appropriate roles (optional for basic usage)
5. Click "Done"

### 3. Create and Download Credentials

1. Click on the created service account
2. Go to "Keys" tab
3. Click "Add Key" > "Create new key"
4. Select "JSON" format
5. Click "Create" - the JSON file will be downloaded
6. Save this file securely (e.g., `./credentials/google-service-account.json`)

**IMPORTANT**: Never commit this credentials file to version control! Add it to your `.gitignore`.

### 4. Share Your Google Sheet

1. Open your Google Sheet
2. Click "Share" button
3. Add the service account email (found in the JSON file as `client_email`)
4. Grant "Editor" permission
5. Click "Send"

### 5. Configure Environment Variables

Add to your `.env` file:

```bash
# Option 1: Path to credentials file (recommended)
GOOGLE_SHEETS_CREDENTIALS_PATH=./credentials/google-service-account.json

# Option 2: Inline JSON (for environments like Heroku)
# GOOGLE_SHEETS_CREDENTIALS_JSON='{"type":"service_account","project_id":"...","private_key":"..."}'
```

## Usage

### Basic Example

```python
from financial_analysis_agent.export import GoogleSheetsClient

# Initialize client
client = GoogleSheetsClient(
    credentials_path='./credentials/google-service-account.json'
)

# Upload CSV file
client.write_csv_to_sheet(
    spreadsheet_id='1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms',
    csv_file='data.csv',
    tab_name='MyData'
)
```

### Write Data Directly

```python
# Prepare data as 2D list
data = [
    ['Ticker', 'Price', 'Volume'],
    ['AAPL', '150.00', '1000000'],
    ['GOOGL', '2800.00', '500000']
]

# Write to sheet
client.write_data_to_sheet(
    spreadsheet_id='1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms',
    data=data,
    tab_name='StockData',
    clear_existing=True
)
```

### Append Data

```python
# Append new rows to existing data
new_data = [
    ['TSLA', '800.00', '750000'],
    ['MSFT', '380.00', '600000']
]

client.append_data_to_sheet(
    spreadsheet_id='1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms',
    data=new_data,
    tab_name='StockData'
)
```

### Format Header Row

```python
# Make header row bold with gray background
client.format_header_row(
    spreadsheet_id='1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms',
    tab_name='StockData',
    bold=True,
    background_color={'red': 0.9, 'green': 0.9, 'blue': 0.9}
)
```

### Using the Command-Line Script

```bash
# Upload earnings data to Google Sheets
python upload_to_google_sheets.py \
  --csv tradingview_earnings.csv \
  --spreadsheet-id 1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms \
  --tab-name "Earnings_2025-11-11"

# Upload without clearing existing data
python upload_to_google_sheets.py \
  --csv aapl_analysis.csv \
  --spreadsheet-id 1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms \
  --tab-name "AAPL_Analysis" \
  --no-clear
```

## Finding Your Spreadsheet ID

The spreadsheet ID is in the URL of your Google Sheet:

```
https://docs.google.com/spreadsheets/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms/edit
                                       ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
                                       This is your spreadsheet ID
```

## Integration with Existing Scripts

### Modifying `fetch_tradingview_earnings.py`

You can integrate Google Sheets export directly into the earnings fetcher:

```python
from financial_analysis_agent.export import GoogleSheetsClient
from financial_analysis_agent.config import get_config

# After saving to CSV
save_to_csv(earnings_data, args.output)

# Also upload to Google Sheets if configured
config = get_config()
credentials_path = config.get("apis.google_sheets.credentials_path")

if credentials_path:
    try:
        client = GoogleSheetsClient(credentials_path=credentials_path)
        client.write_csv_to_sheet(
            spreadsheet_id='YOUR_SPREADSHEET_ID',
            csv_file=args.output,
            tab_name=f'Earnings_{datetime.now().strftime("%Y-%m-%d")}'
        )
        print("✓ Data uploaded to Google Sheets")
    except Exception as e:
        print(f"Warning: Failed to upload to Google Sheets: {e}")
```

## Security Best Practices

1. **Never commit credentials** - Add `*.json` to `.gitignore` for credential files
2. **Use environment variables** - Store sensitive data in `.env` files
3. **Limit service account permissions** - Only grant necessary Google Cloud roles
4. **Rotate credentials regularly** - Create new service account keys periodically
5. **Use separate credentials per environment** - Different keys for dev/staging/prod

## Troubleshooting

### "The caller does not have permission"

- Ensure the service account email is added to the Google Sheet with "Editor" permission
- Check that the Google Sheets API is enabled in your Google Cloud project

### "Service account credentials not found"

- Verify the path in `GOOGLE_SHEETS_CREDENTIALS_PATH` is correct
- Ensure the credentials JSON file exists and is readable

### "Invalid credentials"

- Verify the JSON file is valid (use a JSON validator)
- Ensure you downloaded the correct service account key
- Try creating a new service account key

## API Documentation

See the docstrings in `google_sheets_client.py` for detailed API documentation.

## Dependencies

```
google-auth>=2.23.0
google-auth-oauthlib>=1.1.0
google-auth-httplib2>=0.1.1
google-api-python-client>=2.100.0
```

These are automatically installed when you run:

```bash
pip install -r requirements.txt
```
