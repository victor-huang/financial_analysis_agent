"""
Google Sheets client for writing CSV data to Google Sheets via API.

This module provides a client to authenticate with Google Sheets API and write
CSV data to specific sheets and tabs.
"""

import csv
import logging
from pathlib import Path
from typing import List, Optional, Union

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)


class GoogleSheetsClient:
    """
    Client for interacting with Google Sheets API.

    Supports two authentication methods:
    1. Service Account (recommended for automated scripts)
    2. OAuth 2.0 credentials (for user-based access)

    Examples:
        # Using service account credentials
        client = GoogleSheetsClient(
            credentials_path='/path/to/service-account.json'
        )

        # Write CSV file to a sheet
        client.write_csv_to_sheet(
            spreadsheet_id='1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms',
            csv_file='data.csv',
            tab_name='Sheet1'
        )

        # Write data directly from list
        data = [
            ['Ticker', 'Price', 'Volume'],
            ['AAPL', '150.00', '1000000'],
            ['GOOGL', '2800.00', '500000']
        ]
        client.write_data_to_sheet(
            spreadsheet_id='1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms',
            data=data,
            tab_name='StockData'
        )
    """

    SCOPES = ['https://www.googleapis.com/auth/spreadsheets']

    def __init__(
        self,
        credentials_path: Optional[str] = None,
        service_account_info: Optional[dict] = None
    ):
        """
        Initialize Google Sheets client.

        Args:
            credentials_path: Path to service account JSON credentials file
            service_account_info: Dictionary containing service account credentials
                                 (alternative to credentials_path)

        Raises:
            ValueError: If neither credentials_path nor service_account_info provided
        """
        if not credentials_path and not service_account_info:
            raise ValueError(
                "Must provide either credentials_path or service_account_info"
            )

        self.credentials = self._authenticate(credentials_path, service_account_info)
        self.service = build('sheets', 'v4', credentials=self.credentials)
        logger.info("Google Sheets client initialized successfully")

    def _authenticate(
        self,
        credentials_path: Optional[str],
        service_account_info: Optional[dict]
    ) -> service_account.Credentials:
        """
        Authenticate with Google Sheets API using service account.

        Args:
            credentials_path: Path to credentials JSON file
            service_account_info: Dictionary with service account info

        Returns:
            Authenticated credentials object

        Raises:
            Exception: If authentication fails
        """
        try:
            if credentials_path:
                creds = service_account.Credentials.from_service_account_file(
                    credentials_path, scopes=self.SCOPES
                )
                logger.info(f"Authenticated using credentials from {credentials_path}")
            else:
                creds = service_account.Credentials.from_service_account_info(
                    service_account_info, scopes=self.SCOPES
                )
                logger.info("Authenticated using provided service account info")

            return creds
        except Exception as e:
            logger.error(f"Authentication failed: {e}")
            raise

    def get_or_create_sheet_tab(
        self,
        spreadsheet_id: str,
        tab_name: str
    ) -> int:
        """
        Get sheet tab ID by name, or create it if it doesn't exist.

        Args:
            spreadsheet_id: The ID of the spreadsheet
            tab_name: Name of the tab/sheet

        Returns:
            Sheet ID (integer)

        Raises:
            HttpError: If API request fails
        """
        try:
            # Get existing sheets
            spreadsheet = self.service.spreadsheets().get(
                spreadsheetId=spreadsheet_id
            ).execute()

            sheets = spreadsheet.get('sheets', [])

            # Check if tab already exists
            for sheet in sheets:
                if sheet['properties']['title'] == tab_name:
                    sheet_id = sheet['properties']['sheetId']
                    logger.info(f"Found existing tab '{tab_name}' with ID {sheet_id}")
                    return sheet_id

            # Create new tab if it doesn't exist
            request_body = {
                'requests': [{
                    'addSheet': {
                        'properties': {
                            'title': tab_name
                        }
                    }
                }]
            }

            response = self.service.spreadsheets().batchUpdate(
                spreadsheetId=spreadsheet_id,
                body=request_body
            ).execute()

            sheet_id = response['replies'][0]['addSheet']['properties']['sheetId']
            logger.info(f"Created new tab '{tab_name}' with ID {sheet_id}")
            return sheet_id

        except HttpError as e:
            logger.error(f"Failed to get/create sheet tab: {e}")
            raise

    def clear_sheet_tab(
        self,
        spreadsheet_id: str,
        tab_name: str
    ) -> None:
        """
        Clear all data from a sheet tab.

        Args:
            spreadsheet_id: The ID of the spreadsheet
            tab_name: Name of the tab to clear

        Raises:
            HttpError: If API request fails
        """
        try:
            self.service.spreadsheets().values().clear(
                spreadsheetId=spreadsheet_id,
                range=f"{tab_name}!A1:ZZ"
            ).execute()
            logger.info(f"Cleared data from tab '{tab_name}'")
        except HttpError as e:
            logger.error(f"Failed to clear sheet tab: {e}")
            raise

    def write_data_to_sheet(
        self,
        spreadsheet_id: str,
        data: List[List[Union[str, int, float]]],
        tab_name: str = 'Sheet1',
        clear_existing: bool = True,
        start_cell: str = 'A1'
    ) -> dict:
        """
        Write data to a Google Sheet tab.

        Args:
            spreadsheet_id: The ID of the spreadsheet
            data: 2D list of data to write (rows x columns)
            tab_name: Name of the tab to write to
            clear_existing: Whether to clear existing data before writing
            start_cell: Starting cell for data (e.g., 'A1', 'B2')

        Returns:
            API response dictionary

        Raises:
            HttpError: If API request fails
        """
        try:
            # Ensure tab exists
            self.get_or_create_sheet_tab(spreadsheet_id, tab_name)

            # Clear existing data if requested
            if clear_existing:
                self.clear_sheet_tab(spreadsheet_id, tab_name)

            # Prepare the data
            body = {
                'values': data
            }

            # Write data
            range_name = f"{tab_name}!{start_cell}"
            result = self.service.spreadsheets().values().update(
                spreadsheetId=spreadsheet_id,
                range=range_name,
                valueInputOption='USER_ENTERED',
                body=body
            ).execute()

            updated_cells = result.get('updatedCells', 0)
            logger.info(
                f"Successfully wrote {len(data)} rows to '{tab_name}' "
                f"({updated_cells} cells updated)"
            )

            return result

        except HttpError as e:
            logger.error(f"Failed to write data to sheet: {e}")
            raise

    def write_csv_to_sheet(
        self,
        spreadsheet_id: str,
        csv_file: Union[str, Path],
        tab_name: str = 'Sheet1',
        clear_existing: bool = True,
        start_cell: str = 'A1'
    ) -> dict:
        """
        Write CSV file contents to a Google Sheet tab.

        Args:
            spreadsheet_id: The ID of the spreadsheet
            csv_file: Path to CSV file to read
            tab_name: Name of the tab to write to
            clear_existing: Whether to clear existing data before writing
            start_cell: Starting cell for data (e.g., 'A1', 'B2')

        Returns:
            API response dictionary

        Raises:
            FileNotFoundError: If CSV file doesn't exist
            HttpError: If API request fails
        """
        csv_path = Path(csv_file)

        if not csv_path.exists():
            raise FileNotFoundError(f"CSV file not found: {csv_file}")

        # Read CSV file
        data = []
        with open(csv_path, 'r', encoding='utf-8') as f:
            csv_reader = csv.reader(f)
            data = list(csv_reader)

        if not data:
            logger.warning(f"CSV file {csv_file} is empty")
            return {}

        logger.info(f"Read {len(data)} rows from {csv_file}")

        # Write to sheet
        return self.write_data_to_sheet(
            spreadsheet_id=spreadsheet_id,
            data=data,
            tab_name=tab_name,
            clear_existing=clear_existing,
            start_cell=start_cell
        )

    def append_data_to_sheet(
        self,
        spreadsheet_id: str,
        data: List[List[Union[str, int, float]]],
        tab_name: str = 'Sheet1'
    ) -> dict:
        """
        Append data to the end of a Google Sheet tab.

        Args:
            spreadsheet_id: The ID of the spreadsheet
            data: 2D list of data to append (rows x columns)
            tab_name: Name of the tab to append to

        Returns:
            API response dictionary

        Raises:
            HttpError: If API request fails
        """
        try:
            # Ensure tab exists
            self.get_or_create_sheet_tab(spreadsheet_id, tab_name)

            # Prepare the data
            body = {
                'values': data
            }

            # Append data
            range_name = f"{tab_name}!A1"
            result = self.service.spreadsheets().values().append(
                spreadsheetId=spreadsheet_id,
                range=range_name,
                valueInputOption='USER_ENTERED',
                insertDataOption='INSERT_ROWS',
                body=body
            ).execute()

            updated_cells = result.get('updates', {}).get('updatedCells', 0)
            logger.info(
                f"Successfully appended {len(data)} rows to '{tab_name}' "
                f"({updated_cells} cells updated)"
            )

            return result

        except HttpError as e:
            logger.error(f"Failed to append data to sheet: {e}")
            raise

    def format_header_row(
        self,
        spreadsheet_id: str,
        tab_name: str,
        bold: bool = True,
        background_color: Optional[dict] = None
    ) -> dict:
        """
        Format the header row (first row) of a sheet.

        Args:
            spreadsheet_id: The ID of the spreadsheet
            tab_name: Name of the tab
            bold: Whether to make header text bold
            background_color: RGB color dict, e.g., {'red': 0.8, 'green': 0.8, 'blue': 0.8}

        Returns:
            API response dictionary

        Raises:
            HttpError: If API request fails
        """
        try:
            sheet_id = self.get_or_create_sheet_tab(spreadsheet_id, tab_name)

            requests = []

            # Bold formatting
            if bold:
                requests.append({
                    'repeatCell': {
                        'range': {
                            'sheetId': sheet_id,
                            'startRowIndex': 0,
                            'endRowIndex': 1
                        },
                        'cell': {
                            'userEnteredFormat': {
                                'textFormat': {
                                    'bold': True
                                }
                            }
                        },
                        'fields': 'userEnteredFormat.textFormat.bold'
                    }
                })

            # Background color
            if background_color:
                requests.append({
                    'repeatCell': {
                        'range': {
                            'sheetId': sheet_id,
                            'startRowIndex': 0,
                            'endRowIndex': 1
                        },
                        'cell': {
                            'userEnteredFormat': {
                                'backgroundColor': background_color
                            }
                        },
                        'fields': 'userEnteredFormat.backgroundColor'
                    }
                })

            if not requests:
                return {}

            body = {'requests': requests}
            result = self.service.spreadsheets().batchUpdate(
                spreadsheetId=spreadsheet_id,
                body=body
            ).execute()

            logger.info(f"Formatted header row in '{tab_name}'")
            return result

        except HttpError as e:
            logger.error(f"Failed to format header row: {e}")
            raise
