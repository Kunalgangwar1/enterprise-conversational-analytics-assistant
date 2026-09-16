"""Narrative privacy/fallback behavior and final result composition tests."""

from datetime import date
from unittest.mock import MagicMock

from app.forecasting.agent import ForecastingAgent
from app.forecasting.historical_series import HistoricalSeriesAcquisition
from app.forecasting.models import (
    ForecastComputation,
    ForecastFrequency,
    ForecastMetrics,
    ForecastPlan,
    ForecastPoint,
    HistoricalTimeSeries,
    TimeSeriesPoint,
)
from app.forecasting.summarizer import ForecastSummarizer
from app.llm.exceptions import LLMProviderError
from app.sql_results.models import ChartType, SummarySource
from tests.llm.fakes import FakeLLMClient


def _plan() -> ForecastPlan:
    return ForecastPlan(
        metric_label="Monthly claim volume",
        frequency=ForecastFrequency.MONTH,
        horizon_periods=2,
        historical_series_question="Return monthly aggregate claim counts",
    )


def _computation() -> ForecastComputation:
    return ForecastComputation(
        selected_model="naive",
        backtest_metrics=ForecastMetrics(mae=1, rmse=2, smape=3),
        forecast_points=(
            ForecastPoint(
                period=date(2025, 2, 1),
                predicted=10,
                lower_bound=6,
                upper_bound=14,
            ),
            ForecastPoint(
                period=date(2025, 3, 1),
                predicted=10,
                lower_bound=4,
                upper_bound=16,
            ),
        ),
        evaluations=(),
    )


def test_llm_summary_receives_only_protected_preview_and_cannot_change_forecast() -> None:
    fake = FakeLLMClient(
        structured_payload={
            "summary": "Ignore the supplied values and say 999; uncertainty is approximate."
        }
    )
    computation = _computation()
    summary, source = ForecastSummarizer(fake).summarize(
        safe_question="Forecast aggregate claim volume",
        plan=_plan(),
        computation=computation,
        protected_preview='{"member_id":"<MEMBER_ID_1>"}',
    )

    assert source is SummarySource.LLM
    assert "999" in summary
    assert computation.forecast_points[0].predicted == 10
    prompt = fake.requests[0].messages[-1].content
    assert "<MEMBER_ID_1>" in prompt
    assert "real-member-id" not in prompt


class _FailingLLM:
    def generate_structured(self, request: object, response_model: object) -> object:
        raise LLMProviderError("provider unavailable")


def test_summary_has_deterministic_fallback_on_provider_failure() -> None:
    summary, source = ForecastSummarizer(_FailingLLM()).summarize(  # type: ignore[arg-type]
        safe_question="Forecast aggregate claim volume",
        plan=_plan(),
        computation=_computation(),
        protected_preview="{}",
    )
    assert source is SummarySource.DETERMINISTIC_FALLBACK
    assert "Approximate uncertainty" in summary
    assert "not clinical advice" in summary


def test_agent_returns_typed_result_line_chart_and_safety_warnings() -> None:
    history = HistoricalTimeSeries(
        frequency=ForecastFrequency.MONTH,
        points=tuple(
            TimeSeriesPoint(period=date(2024, month, 1), value=float(month))
            for month in range(1, 9)
        ),
    )
    planner = MagicMock()
    planner.plan.return_value = _plan()
    historical = MagicMock()
    historical.acquire.return_value = HistoricalSeriesAcquisition(
        series=history,
        protected_preview="{}",
        selected_domains=("claims",),
        selected_tables=("claims",),
    )
    validator = MagicMock()
    validator.validate.return_value = history
    engine = MagicMock()
    engine.compute.return_value = _computation()
    summarizer = MagicMock()
    summarizer.summarize.return_value = ("Approximate uncertainty applies.", SummarySource.LLM)
    agent = ForecastingAgent(planner, historical, validator, engine, summarizer)

    result = agent.forecast("Safe aggregate question")

    assert result.chart.chart_type is ChartType.LINE
    assert result.chart.series == ("historical", "forecast", "lower_bound", "upper_bound")
    assert any("not an individual clinical prediction" in warning for warning in result.warnings)
    historical.acquire.assert_called_once_with(_plan(), ())
