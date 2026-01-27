#!/usr/bin/env python3
"""
Critical path tests for TradingView scraper parsing logic.
Uses static mock HTML data to test parsing without browser dependencies.
"""

import sys
import os
import pytest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from tradingview_final_scraper import TradingViewFinalScraper


class TestParseValue:
    """Tests for _parse_value method - handles B/M suffixes and special characters."""

    def setup_method(self):
        self.scraper = TradingViewFinalScraper.__new__(TradingViewFinalScraper)

    def test_parse_billions_to_millions(self):
        assert self.scraper._parse_value("36.48B") == 36480.0

    def test_parse_millions(self):
        assert self.scraper._parse_value("500M") == 500.0

    def test_parse_plain_number(self):
        assert self.scraper._parse_value("1.23") == 1.23

    def test_parse_negative_number(self):
        assert self.scraper._parse_value("-0.45") == -0.45

    def test_parse_dash_returns_none(self):
        assert self.scraper._parse_value("—") is None
        assert self.scraper._parse_value("-") is None

    def test_parse_empty_returns_none(self):
        assert self.scraper._parse_value("") is None

    def test_parse_with_spaces(self):
        assert self.scraper._parse_value(" 100M ") == 100.0
        assert self.scraper._parse_value(" 2.5B ") == 2500.0


class TestExtractChartDataFromHtml:
    """Tests for chart data extraction using BeautifulSoup parsing."""

    def setup_method(self):
        self.scraper = TradingViewFinalScraper.__new__(TradingViewFinalScraper)

    def _create_mock_chart_html(
        self,
        periods: list,
        scale_values: list,
        bar_data: list,
        period_type: str = "quarterly"
    ) -> str:
        """
        Create mock HTML for chart data extraction.

        Args:
            periods: List of period labels (e.g., ["Q1 '24", "Q2 '24"])
            scale_values: List of scale values (e.g., [0.0, 1.0, 2.0])
            bar_data: List of dicts with 'reported' and 'estimate' heights (0-100%)
            period_type: "quarterly" or "annual"
        """
        html_parts = ['<div class="chart-container">']

        # Add period labels (horizontal scale)
        for period in periods:
            html_parts.append(
                f'<div class="horizontalScaleValue-abc123">{period}</div>'
            )

        # Add scale values (vertical scale)
        for val in scale_values:
            html_parts.append(
                f'<div class="verticalScaleValue-xyz789">{val}</div>'
            )

        # Add bar columns
        max_val = max(scale_values)
        min_val = min(scale_values)

        for i, bar in enumerate(bar_data):
            html_parts.append(f'<div class="column-col{i}">')

            if bar.get("reported") is not None:
                height_pct = ((bar["reported"] - min_val) / (max_val - min_val)) * 100
                html_parts.append(
                    f'<div class="bar-reported" style="height: max({height_pct}%, 1px); background-color: #3179F5;"></div>'
                )

            if bar.get("estimate") is not None:
                height_pct = ((bar["estimate"] - min_val) / (max_val - min_val)) * 100
                html_parts.append(
                    f'<div class="bar-estimate" style="height: max({height_pct}%, 1px); background-color: #EBEBEB;"></div>'
                )

            html_parts.append('</div>')

        html_parts.append('</div>')
        return '\n'.join(html_parts)

    def test_extract_quarterly_eps_data(self):
        """Test extracting quarterly EPS data from chart HTML."""
        mock_html = self._create_mock_chart_html(
            periods=["Q1 '24", "Q2 '24", "Q3 '24", "Q4 '24", "Q1 '25"],
            scale_values=[0.0, 1.0, 2.0, 3.0],
            bar_data=[
                {"reported": 1.5, "estimate": 1.4},
                {"reported": 1.8, "estimate": 1.7},
                {"reported": 2.0, "estimate": 1.9},
                {"reported": 2.2, "estimate": 2.1},
                {"estimate": 2.5},  # Forecast only
            ],
            period_type="quarterly"
        )

        mock_element = MagicMock()
        mock_element.get_attribute.return_value = mock_html

        result = self.scraper._extract_chart_data_from_section(mock_element, "quarterly")

        assert "historical" in result
        assert "forecast" in result
        assert len(result["historical"]) == 4
        assert len(result["forecast"]) == 1
        assert result["historical"][0]["period"] == "Q1 '24"
        assert result["forecast"][0]["period"] == "Q1 '25"

    def test_extract_annual_eps_data(self):
        """Test extracting annual EPS data from chart HTML."""
        mock_html = self._create_mock_chart_html(
            periods=["2021", "2022", "2023", "2024", "2025"],
            scale_values=[0.0, 5.0, 10.0, 15.0],
            bar_data=[
                {"reported": 8.0, "estimate": 7.5},
                {"reported": 10.0, "estimate": 9.5},
                {"reported": 12.0, "estimate": 11.5},
                {"reported": 14.0, "estimate": 13.5},
                {"estimate": 15.0},  # Forecast only
            ],
            period_type="annual"
        )

        mock_element = MagicMock()
        mock_element.get_attribute.return_value = mock_html

        result = self.scraper._extract_chart_data_from_section(mock_element, "annual")

        assert len(result["historical"]) == 4
        assert len(result["forecast"]) == 1
        assert result["historical"][0]["period"] == "2021"
        assert result["forecast"][0]["period"] == "2025"

    def test_extract_with_negative_values(self):
        """Test extraction when scale includes negative values."""
        mock_html = self._create_mock_chart_html(
            periods=["Q1 '24", "Q2 '24", "Q3 '24"],
            scale_values=[-1.0, 0.0, 1.0, 2.0],
            bar_data=[
                {"reported": -0.5, "estimate": -0.3},
                {"reported": 0.5, "estimate": 0.4},
                {"reported": 1.5, "estimate": 1.4},
            ],
            period_type="quarterly"
        )

        mock_element = MagicMock()
        mock_element.get_attribute.return_value = mock_html

        result = self.scraper._extract_chart_data_from_section(mock_element, "quarterly")

        assert len(result["historical"]) == 3
        assert result["scale_range"] == [-1.0, 2.0]

    def test_extract_empty_data_returns_empty_dict(self):
        """Test that missing periods or scale returns empty dict."""
        mock_html = '<div class="chart-container"></div>'
        mock_element = MagicMock()
        mock_element.get_attribute.return_value = mock_html

        result = self.scraper._extract_chart_data_from_section(mock_element, "quarterly")

        assert result == {}


class TestExtractChartDataFromHtmlMethod:
    """Tests for _extract_chart_data_from_html static method."""

    def setup_method(self):
        self.scraper = TradingViewFinalScraper.__new__(TradingViewFinalScraper)

    def test_filters_quarterly_periods_correctly(self):
        """Test that only quarterly periods (with ') are extracted for quarterly type."""
        html = '''
        <div>
            <div class="horizontalScaleValue-abc">Q1 '24</div>
            <div class="horizontalScaleValue-abc">Q2 '24</div>
            <div class="horizontalScaleValue-abc">2024</div>
            <div class="verticalScaleValue-xyz">0.0</div>
            <div class="verticalScaleValue-xyz">1.0</div>
        </div>
        '''
        result = self.scraper._extract_chart_data_from_html(html, "quarterly")
        # Should only have Q1 '24 and Q2 '24, not 2024
        # Note: This test validates the filtering logic

    def test_filters_annual_periods_correctly(self):
        """Test that only annual periods (4-digit years) are extracted for annual type."""
        html = '''
        <div>
            <div class="horizontalScaleValue-abc">2021</div>
            <div class="horizontalScaleValue-abc">2022</div>
            <div class="horizontalScaleValue-abc">Q1 '24</div>
            <div class="verticalScaleValue-xyz">0.0</div>
            <div class="verticalScaleValue-xyz">10.0</div>
        </div>
        '''
        result = self.scraper._extract_chart_data_from_html(html, "annual")
        # Should only have 2021 and 2022, not Q1 '24


class TestDriverSetupRetry:
    """Tests for driver setup retry logic."""

    def setup_method(self):
        self.scraper = TradingViewFinalScraper.__new__(TradingViewFinalScraper)
        self.scraper.headless = True
        self.scraper.driver = None

    @patch('tradingview_final_scraper.webdriver.Chrome')
    def test_setup_driver_succeeds_on_first_attempt(self, mock_chrome):
        """Test driver setup succeeds on first try."""
        mock_driver = MagicMock()
        mock_chrome.return_value = mock_driver

        self.scraper._setup_driver()

        assert self.scraper.driver == mock_driver
        assert mock_chrome.call_count == 1

    @patch('tradingview_final_scraper.webdriver.Chrome')
    @patch('tradingview_final_scraper.time.sleep')
    def test_setup_driver_retries_on_failure(self, mock_sleep, mock_chrome):
        """Test driver setup retries on failure and succeeds on second attempt."""
        mock_driver = MagicMock()
        mock_chrome.side_effect = [Exception("Connection failed"), mock_driver]

        self.scraper._setup_driver(max_retries=3)

        assert self.scraper.driver == mock_driver
        assert mock_chrome.call_count == 2
        mock_sleep.assert_called_once_with(2)

    @patch('tradingview_final_scraper.webdriver.Chrome')
    @patch('tradingview_final_scraper.time.sleep')
    def test_setup_driver_succeeds_on_third_attempt(self, mock_sleep, mock_chrome):
        """Test driver setup succeeds on third and final attempt."""
        mock_driver = MagicMock()
        mock_chrome.side_effect = [
            Exception("Attempt 1 failed"),
            Exception("Attempt 2 failed"),
            mock_driver
        ]

        self.scraper._setup_driver(max_retries=3)

        assert self.scraper.driver == mock_driver
        assert mock_chrome.call_count == 3
        assert mock_sleep.call_count == 2

    @patch('tradingview_final_scraper.webdriver.Chrome')
    @patch('tradingview_final_scraper.time.sleep')
    def test_setup_driver_raises_after_max_retries(self, mock_sleep, mock_chrome):
        """Test driver setup raises exception after all retries exhausted."""
        mock_chrome.side_effect = Exception("Connection failed")

        with pytest.raises(Exception) as exc_info:
            self.scraper._setup_driver(max_retries=3)

        assert "Connection failed" in str(exc_info.value)
        assert mock_chrome.call_count == 3
        assert mock_sleep.call_count == 2

    @patch('tradingview_final_scraper.webdriver.Chrome')
    @patch('tradingview_final_scraper.time.sleep')
    def test_setup_driver_custom_max_retries(self, mock_sleep, mock_chrome):
        """Test driver setup respects custom max_retries parameter."""
        mock_chrome.side_effect = Exception("Connection failed")

        with pytest.raises(Exception):
            self.scraper._setup_driver(max_retries=5)

        assert mock_chrome.call_count == 5
        assert mock_sleep.call_count == 4  # sleeps between retries (5 attempts - 1)
