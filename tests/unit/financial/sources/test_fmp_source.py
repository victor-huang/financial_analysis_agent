"""Unit tests for FMPSource income statement, cash flow, ratios, and key metrics."""
import pandas as pd
import pytest

from financial_analysis_agent.financial.sources.fmp_source import FMPSource


def _mock_response(mocker, payload):
    response = mocker.Mock()
    response.json.return_value = payload
    response.raise_for_status.return_value = None
    return response


class TestGetIncomeStatement:
    def test_returns_dataframe_on_success(self, mocker):
        payload = [{"date": "2025-09-27", "period": "FY", "revenue": 416161000000,
                     "grossProfit": 195201000000, "ebitda": 144427000000,
                     "operatingIncome": 133050000000, "netIncome": 112010000000}]
        get = mocker.patch(
            "financial_analysis_agent.financial.sources.fmp_source.requests.get",
            return_value=_mock_response(mocker, payload),
        )
        source = FMPSource("test-key")

        df = source.get_income_statement("AAPL", period="annual", limit=1)

        assert df is not None
        assert df.iloc[0]["grossProfit"] == 195201000000
        assert get.call_args.kwargs["params"]["period"] == "annual"

    def test_maps_quarterly_period_to_fmp_quarter_param(self, mocker):
        get = mocker.patch(
            "financial_analysis_agent.financial.sources.fmp_source.requests.get",
            return_value=_mock_response(mocker, [{"date": "2025-06-27", "revenue": 1}]),
        )
        source = FMPSource("test-key")

        source.get_income_statement("AAPL", period="quarterly", limit=1)

        assert get.call_args.kwargs["params"]["period"] == "quarter"

    def test_returns_none_when_api_returns_no_data(self, mocker):
        mocker.patch(
            "financial_analysis_agent.financial.sources.fmp_source.requests.get",
            return_value=_mock_response(mocker, {"Error Message": "Invalid API KEY"}),
        )
        source = FMPSource("bad-key")

        df = source.get_income_statement("AAPL")

        assert df is None


class TestGetCashFlowStatement:
    def test_returns_dataframe_on_success(self, mocker):
        payload = [{"date": "2025-09-27", "operatingCashFlow": 111482000000, "freeCashFlow": 98767000000}]
        mocker.patch(
            "financial_analysis_agent.financial.sources.fmp_source.requests.get",
            return_value=_mock_response(mocker, payload),
        )
        source = FMPSource("test-key")

        df = source.get_cash_flow_statement("AAPL")

        assert df.iloc[0]["freeCashFlow"] == 98767000000

    def test_returns_none_when_api_returns_no_data(self, mocker):
        mocker.patch(
            "financial_analysis_agent.financial.sources.fmp_source.requests.get",
            return_value=_mock_response(mocker, []),
        )
        source = FMPSource("test-key")

        assert source.get_cash_flow_statement("AAPL") is None


class TestGetRatios:
    def test_returns_dataframe_on_success(self, mocker):
        payload = [{"date": "2025-09-27", "grossProfitMargin": 0.469, "ebitdaMargin": 0.347,
                     "operatingProfitMargin": 0.32, "netProfitMargin": 0.269}]
        mocker.patch(
            "financial_analysis_agent.financial.sources.fmp_source.requests.get",
            return_value=_mock_response(mocker, payload),
        )
        source = FMPSource("test-key")

        df = source.get_ratios("AAPL")

        assert df.iloc[0]["ebitdaMargin"] == pytest.approx(0.347)


class TestGetKeyMetrics:
    def _stub_source(self, mocker, income, cash_flow, ratios):
        source = FMPSource("test-key")
        mocker.patch.object(source, "get_income_statement", return_value=income)
        mocker.patch.object(source, "get_cash_flow_statement", return_value=cash_flow)
        mocker.patch.object(source, "get_ratios", return_value=ratios)
        return source

    def test_merges_income_cash_flow_and_ratios(self, mocker):
        income = pd.DataFrame([{"date": "2025-09-27", "period": "FY", "revenue": 416161000000,
                                  "grossProfit": 195201000000, "ebitda": 144427000000,
                                  "operatingIncome": 133050000000, "netIncome": 112010000000}])
        cash_flow = pd.DataFrame([{"date": "2025-09-27", "operatingCashFlow": 111482000000,
                                     "freeCashFlow": 98767000000}])
        ratios = pd.DataFrame([{"date": "2025-09-27", "grossProfitMargin": 0.46905164,
                                  "ebitdaMargin": 0.34704597, "operatingProfitMargin": 0.31970800,
                                  "netProfitMargin": 0.26915064}])
        source = self._stub_source(mocker, income, cash_flow, ratios)

        result = source.get_key_metrics("AAPL", period="annual", limit=1)

        row = result.iloc[0]
        assert row["gross_profit"] == 195201000000
        assert row["ebitda"] == 144427000000
        assert row["free_cash_flow"] == 98767000000
        assert row["gross_margin"] == pytest.approx(46.905164)
        assert row["ebitda_margin"] == pytest.approx(34.704597)
        assert row["free_cash_flow_margin"] == pytest.approx(98767000000 / 416161000000 * 100)

    def test_computes_margins_from_income_statement_when_ratios_unavailable(self, mocker):
        income = pd.DataFrame([{"date": "2025-09-27", "period": "FY", "revenue": 200,
                                  "grossProfit": 100, "ebitda": 60, "operatingIncome": 50, "netIncome": 20}])
        cash_flow = pd.DataFrame([{"date": "2025-09-27", "operatingCashFlow": 40, "freeCashFlow": 30}])
        source = self._stub_source(mocker, income, cash_flow, ratios=None)

        result = source.get_key_metrics("AAPL")

        row = result.iloc[0]
        assert row["gross_margin"] == pytest.approx(50.0)
        assert row["ebitda_margin"] == pytest.approx(30.0)
        assert row["operating_margin"] == pytest.approx(25.0)
        assert row["net_margin"] == pytest.approx(10.0)
        assert row["free_cash_flow_margin"] == pytest.approx(15.0)

    def test_returns_none_when_income_statement_missing(self, mocker):
        source = self._stub_source(mocker, income=None, cash_flow=None, ratios=None)

        assert source.get_key_metrics("AAPL") is None

    def test_sorts_multiple_periods_descending_by_date(self, mocker):
        income = pd.DataFrame([
            {"date": "2023-09-30", "period": "FY", "revenue": 100, "grossProfit": 40,
             "ebitda": 30, "operatingIncome": 25, "netIncome": 15},
            {"date": "2025-09-27", "period": "FY", "revenue": 200, "grossProfit": 90,
             "ebitda": 60, "operatingIncome": 50, "netIncome": 30},
        ])
        source = self._stub_source(mocker, income, cash_flow=None, ratios=None)

        result = source.get_key_metrics("AAPL", limit=2)

        assert list(result["date"].dt.strftime("%Y-%m-%d")) == ["2025-09-27", "2023-09-30"]
