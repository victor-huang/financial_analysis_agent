#!/usr/bin/env python3
"""
Tests for employee_data_scraper.py
Tests driver retry logic and employee data parsing.
"""

import sys
import os
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from employee_data_scraper import EmployeeDataScraper


class TestEmployeeDataParseValue:
    """Tests for employee data parsing logic."""

    def setup_method(self):
        self.scraper = EmployeeDataScraper.__new__(EmployeeDataScraper)
        self.scraper.headless = True
        self.scraper.driver = None

    def test_parse_employee_count_with_k_suffix(self):
        """Test parsing employee count with K suffix (thousands)."""
        html = '<div>166 K employees</div>'
        result = self.scraper._parse_employee_data(html)

        assert result is not None
        assert result["employee_count"] == 166000

    def test_parse_employee_count_plain(self):
        """Test parsing employee count without K suffix."""
        html = '<div>205 employees</div>'
        result = self.scraper._parse_employee_data(html)

        assert result is not None
        assert result["employee_count"] == 205

    def test_parse_employee_count_with_comma(self):
        """Test parsing employee count with comma separator."""
        html = '<div>1,234 employees</div>'
        result = self.scraper._parse_employee_data(html)

        assert result is not None
        assert result["employee_count"] == 1234

    def test_parse_no_employee_data_returns_none(self):
        """Test that missing employee data returns None."""
        html = '<div>No employee information available</div>'
        result = self.scraper._parse_employee_data(html)

        assert result is None


class TestEmployeeScraperDriverRetry:
    """Tests for employee scraper driver setup retry logic."""

    def setup_method(self):
        self.scraper = EmployeeDataScraper.__new__(EmployeeDataScraper)
        self.scraper.headless = True
        self.scraper.driver = None

    @patch('employee_data_scraper.webdriver.Chrome')
    def test_setup_driver_succeeds_on_first_attempt(self, mock_chrome):
        """Test driver setup succeeds on first try."""
        mock_driver = MagicMock()
        mock_chrome.return_value = mock_driver

        self.scraper._setup_driver()

        assert self.scraper.driver == mock_driver
        assert mock_chrome.call_count == 1

    @patch('employee_data_scraper.webdriver.Chrome')
    def test_setup_driver_skips_if_driver_exists(self, mock_chrome):
        """Test driver setup skips if driver already exists."""
        existing_driver = MagicMock()
        self.scraper.driver = existing_driver

        self.scraper._setup_driver()

        assert self.scraper.driver == existing_driver
        mock_chrome.assert_not_called()

    @patch('employee_data_scraper.webdriver.Chrome')
    @patch('employee_data_scraper.time.sleep')
    def test_setup_driver_retries_on_failure(self, mock_sleep, mock_chrome):
        """Test driver setup retries on failure and succeeds on second attempt."""
        mock_driver = MagicMock()
        mock_chrome.side_effect = [Exception("Connection failed"), mock_driver]

        self.scraper._setup_driver(max_retries=3)

        assert self.scraper.driver == mock_driver
        assert mock_chrome.call_count == 2
        mock_sleep.assert_called_once_with(2)

    @patch('employee_data_scraper.webdriver.Chrome')
    @patch('employee_data_scraper.time.sleep')
    def test_setup_driver_raises_after_max_retries(self, mock_sleep, mock_chrome):
        """Test driver setup raises exception after all retries exhausted."""
        import pytest
        mock_chrome.side_effect = Exception("Connection failed")

        with pytest.raises(Exception) as exc_info:
            self.scraper._setup_driver(max_retries=3)

        assert "Connection failed" in str(exc_info.value)
        assert mock_chrome.call_count == 3
        assert mock_sleep.call_count == 2
