"""Forecast planning, bounds, configuration, and scope policy tests."""

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.forecasting.exceptions import (
    ForecastHorizonError,
    ForecastPlanningError,
    ForecastScopeError,
)
from app.forecasting.models import ForecastFrequency
from app.forecasting.planner import ForecastPlanner
from tests.llm.fakes import FakeLLMClient


def _payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "metric_label": "Monthly claim volume",
        "frequency": "month",
        "historical_series_question": (
            "Return monthly aggregate claim counts in chronological order"
        ),
    }
    payload.update(overrides)
    return payload


def test_planner_applies_default_horizon_and_emits_natural_language_question() -> None:
    planner = ForecastPlanner(
        FakeLLMClient(structured_payload=_payload()),
        default_horizon=3,
        max_horizon=12,
    )

    plan = planner.plan("Forecast aggregate monthly claim volume")

    assert plan.frequency is ForecastFrequency.MONTH
    assert plan.horizon_periods == 3
    assert plan.historical_series_question.startswith("Return monthly")


def test_forecast_settings_have_phase_17_defaults() -> None:
    settings = Settings(_env_file=None)
    assert (
        settings.forecast_default_horizon,
        settings.forecast_max_horizon,
        settings.forecast_min_history_points,
        settings.forecast_max_history_points,
        settings.forecast_backtest_points,
        settings.forecast_moving_average_window,
        settings.forecast_interval_z,
    ) == (3, 12, 8, 120, 4, 3, 1.96)


def test_planner_preserves_valid_explicit_horizon() -> None:
    planner = ForecastPlanner(
        FakeLLMClient(structured_payload=_payload(horizon_periods=6)),
        default_horizon=3,
        max_horizon=12,
    )
    assert planner.plan("Forecast aggregate monthly claims for six months").horizon_periods == 6


def test_planner_rejects_horizon_above_policy() -> None:
    planner = ForecastPlanner(
        FakeLLMClient(structured_payload=_payload(horizon_periods=13)),
        default_horizon=3,
        max_horizon=12,
    )
    with pytest.raises(ForecastHorizonError):
        planner.plan("Forecast aggregate claims")


@pytest.mark.parametrize(
    "payload",
    [
        _payload(frequency="quarter"),
        _payload(historical_series_question="SELECT month, COUNT(*) FROM claims"),
        _payload(historical_series_question="Use https://example.test/data"),
    ],
)
def test_planner_rejects_invalid_or_executable_structured_output(
    payload: dict[str, object],
) -> None:
    planner = ForecastPlanner(
        FakeLLMClient(structured_payload=payload), default_horizon=3, max_horizon=12
    )
    with pytest.raises(ForecastPlanningError):
        planner.plan("Forecast aggregate claims")


@pytest.mark.parametrize(
    "question",
    [
        "Predict this patient's diagnosis next month",
        "Estimate mortality for individual member T12345",
    ],
)
def test_individual_clinical_predictions_are_rejected_before_llm(question: str) -> None:
    fake = FakeLLMClient(structured_payload=_payload())
    planner = ForecastPlanner(fake, default_horizon=3, max_horizon=12)
    with pytest.raises(ForecastScopeError):
        planner.plan(question)
    assert fake.requests == []


def test_aggregate_operational_forecast_is_allowed() -> None:
    planner = ForecastPlanner(
        FakeLLMClient(structured_payload=_payload()), default_horizon=3, max_horizon=12
    )
    assert planner.plan("Forecast total monthly claim volume").metric_label


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"forecast_default_horizon": 5, "forecast_max_horizon": 4}, "MAX_HORIZON"),
        (
            {"forecast_min_history_points": 12, "forecast_max_history_points": 10},
            "MAX_HISTORY_POINTS",
        ),
        ({"forecast_min_history_points": 8, "forecast_backtest_points": 8}, "BACKTEST_POINTS"),
    ],
)
def test_forecast_setting_relationships_are_validated(
    overrides: dict[str, int], message: str
) -> None:
    with pytest.raises(ValidationError, match=message):
        Settings(_env_file=None, **overrides)
