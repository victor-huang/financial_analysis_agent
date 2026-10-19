"""Unit tests for CompanyFundamentals profitability and cash flow metrics."""
import pandas as pd
import pytest

from financial_analysis_agent.financial.fundamentals import CompanyFundamentals


def _statement(rows, dates):
    return pd.DataFrame(rows, index=pd.to_datetime(dates))


def _build_fundamentals(mocker, income_rows, balance_rows, cash_flow_rows, dates, fmp_key_metrics=None):
    data_fetcher = mocker.Mock()
    data_fetcher.get_financials.side_effect = lambda ticker, statement_type, period: {
        "income": _statement(income_rows, dates),
        "balance": _statement(balance_rows, dates),
        "cashflow": _statement(cash_flow_rows, dates),
    }[statement_type]
    data_fetcher.get_key_metrics_fmp.return_value = fmp_key_metrics

    return CompanyFundamentals("AAPL", data_fetcher=data_fetcher)


BALANCE_ROW = {
    "Total Assets": 1000, "Total Liabilities": 400, "Total Equity": 600,
    "Total Current Assets": 300, "Total Current Liabilities": 150, "Inventory": 50,
}
CASH_FLOW_ROW = {"Total Cash From Operating Activities": 120, "Capital Expenditures": -20}
INCOME_ROW = {
    "Total Revenue": 1000, "Gross Profit": 500, "EBITDA": 300,
    "Operating Income": 250, "Net Income": 150,
}


class TestGetFinancialRatios:
    def test_computes_metrics_from_yfinance_statements_when_fmp_unavailable(self, mocker):
        fundamentals = _build_fundamentals(
            mocker, [INCOME_ROW], [BALANCE_ROW], [CASH_FLOW_ROW], ["2025-09-30"], fmp_key_metrics=None
        )

        ratios = fundamentals.get_financial_ratios(period="annual")

        assert ratios["gross_profit"] == 500
        assert ratios["gross_margin"] == pytest.approx(50.0)
        assert ratios["ebitda"] == 300
        assert ratios["ebitda_margin"] == pytest.approx(30.0)
        assert ratios["operating_income"] == 250
        assert ratios["operating_margin"] == pytest.approx(25.0)
        assert ratios["net_income"] == 150
        assert ratios["net_margin"] == pytest.approx(15.0)
        assert ratios["free_cash_flow"] == 100  # 120 operating cash flow - 20 capex
        assert ratios["free_cash_flow_margin"] == pytest.approx(10.0)

    def test_overrides_metrics_with_fmp_values_when_available(self, mocker):
        fmp_df = pd.DataFrame([{
            "gross_profit": 555, "gross_margin": 55.5, "ebitda": 333, "ebitda_margin": 33.3,
            "operating_income": 222, "operating_margin": 22.2, "net_income": 111, "net_margin": 11.1,
            "free_cash_flow": 99, "free_cash_flow_margin": 9.9,
        }])
        fundamentals = _build_fundamentals(
            mocker, [INCOME_ROW], [BALANCE_ROW], [CASH_FLOW_ROW], ["2025-09-30"], fmp_key_metrics=fmp_df
        )

        ratios = fundamentals.get_financial_ratios(period="annual")

        assert ratios["gross_profit"] == 555
        assert ratios["ebitda_margin"] == pytest.approx(33.3)
        assert ratios["net_income"] == 111
        assert ratios["free_cash_flow"] == 99

    def test_returns_empty_dict_when_financials_fail_to_load(self, mocker):
        data_fetcher = mocker.Mock()
        data_fetcher.get_financials.return_value = None
        fundamentals = CompanyFundamentals("AAPL", data_fetcher=data_fetcher)

        assert fundamentals.get_financial_ratios(period="annual") == {}


class TestGetPeriodicRatios:
    def test_computes_series_from_yfinance_statements_when_fmp_unavailable(self, mocker):
        income_rows = [
            {"Total Revenue": 1000, "Gross Profit": 500, "EBITDA": 300, "Operating Income": 250, "Net Income": 150},
            {"Total Revenue": 800, "Gross Profit": 400, "EBITDA": 240, "Operating Income": 200, "Net Income": 120},
        ]
        dates = ["2025-09-30", "2024-09-30"]
        fundamentals = _build_fundamentals(
            mocker, income_rows, [BALANCE_ROW, BALANCE_ROW], [CASH_FLOW_ROW, CASH_FLOW_ROW], dates,
            fmp_key_metrics=None,
        )

        series = fundamentals.get_periodic_ratios(period="annual", count=2)

        assert series["label"] == ["2025", "2024"]
        assert series["gross_profit"] == [500, 400]
        assert series["ebitda_margin"] == [pytest.approx(30.0), pytest.approx(30.0)]
        assert series["net_income"] == [150, 120]
        assert series["free_cash_flow"] == [100, 100]

    def test_overrides_each_period_with_matching_fmp_row(self, mocker):
        income_rows = [
            {"Total Revenue": 1000, "Gross Profit": 500, "EBITDA": 300, "Operating Income": 250, "Net Income": 150},
            {"Total Revenue": 800, "Gross Profit": 400, "EBITDA": 240, "Operating Income": 200, "Net Income": 120},
        ]
        dates = ["2025-09-30", "2024-09-30"]
        fmp_df = pd.DataFrame([
            {"gross_profit": 555, "gross_margin": 55.5, "ebitda": 333, "ebitda_margin": 33.3,
             "operating_income": 222, "operating_margin": 22.2, "net_income": 111, "net_margin": 11.1,
             "free_cash_flow": 99, "free_cash_flow_margin": 9.9},
            {"gross_profit": 444, "gross_margin": 44.4, "ebitda": 222, "ebitda_margin": 22.2,
             "operating_income": 111, "operating_margin": 11.1, "net_income": 55, "net_margin": 5.5,
             "free_cash_flow": 88, "free_cash_flow_margin": 8.8},
        ])
        fundamentals = _build_fundamentals(
            mocker, income_rows, [BALANCE_ROW, BALANCE_ROW], [CASH_FLOW_ROW, CASH_FLOW_ROW], dates,
            fmp_key_metrics=fmp_df,
        )

        series = fundamentals.get_periodic_ratios(period="annual", count=2)

        assert series["gross_profit"] == [555, 444]
        assert series["ebitda_margin"] == [pytest.approx(33.3), pytest.approx(22.2)]
        assert series["net_income"] == [111, 55]
        assert series["free_cash_flow"] == [99, 88]

    def test_returns_empty_dict_when_financials_fail_to_load(self, mocker):
        data_fetcher = mocker.Mock()
        data_fetcher.get_financials.return_value = None
        fundamentals = CompanyFundamentals("AAPL", data_fetcher=data_fetcher)

        assert fundamentals.get_periodic_ratios(period="annual", count=2) == {}
