"""Deterministic model, backtest, interval, and calendar tests."""

from datetime import date

import pytest

from app.forecasting.backtest import BacktestSelector, calculate_metrics
from app.forecasting.engine import ForecastEngine
from app.forecasting.forecast_models import (
    LinearTrendModel,
    MovingAverageModel,
    NaiveModel,
    SeasonalNaiveModel,
)
from app.forecasting.models import (
    ForecastFrequency,
    ForecastPlan,
    HistoricalTimeSeries,
    TimeSeriesPoint,
)
from app.forecasting.periods import next_period


def test_models_produce_expected_dependency_free_forecasts() -> None:
    naive = NaiveModel()
    naive.fit((1.0, 2.0, 3.0))
    assert naive.predict(2) == (3.0, 3.0)

    moving = MovingAverageModel(3)
    moving.fit((1.0, 2.0, 3.0))
    assert moving.predict(2) == pytest.approx((2.0, 7 / 3))

    trend = LinearTrendModel()
    trend.fit((2.0, 4.0, 6.0, 8.0))
    assert trend.predict(2) == pytest.approx((10.0, 12.0))

    seasonal = SeasonalNaiveModel(3)
    seasonal.fit((1.0, 2.0, 3.0, 4.0, 5.0, 6.0))
    assert seasonal.predict(4) == (4.0, 5.0, 6.0, 4.0)


def test_metrics_are_zero_safe_and_model_ties_are_stable() -> None:
    metrics = calculate_metrics((0.0, 0.0), (0.0, 0.0))
    assert metrics.mae == metrics.rmse == metrics.smape == 0
    selection = BacktestSelector(2).select((1.0,) * 8, (NaiveModel, LinearTrendModel))
    assert selection.evaluation.model_name == "linear_trend"


class _RecordingModel:
    name = "recording"
    minimum_history = 1
    fitted: list[tuple[float, ...]] = []

    def fit(self, values: tuple[float, ...]) -> None:
        self.fitted.append(values)
        self._last = values[-1]

    def predict(self, horizon: int) -> tuple[float, ...]:
        return (self._last,) * horizon


def test_backtest_fit_excludes_holdout_data() -> None:
    _RecordingModel.fitted.clear()
    BacktestSelector(3).select(tuple(float(value) for value in range(10)), (_RecordingModel,))
    assert _RecordingModel.fitted == [tuple(float(value) for value in range(7))]


@pytest.mark.parametrize(
    ("frequency", "period", "expected"),
    [
        (ForecastFrequency.DAY, date(2024, 1, 31), date(2024, 2, 1)),
        (ForecastFrequency.WEEK, date(2024, 1, 31), date(2024, 2, 7)),
        (ForecastFrequency.MONTH, date(2024, 1, 31), date(2024, 2, 29)),
        (ForecastFrequency.MONTH, date(2024, 2, 29), date(2024, 3, 31)),
    ],
)
def test_calendar_period_advancement(
    frequency: ForecastFrequency, period: date, expected: date
) -> None:
    assert next_period(period, frequency) == expected


def test_engine_refits_winner_on_all_history_and_clamps_nonnegative_forecasts() -> None:
    points = tuple(
        TimeSeriesPoint(period=date(2024, month, 1), value=float(13 - month))
        for month in range(1, 13)
    )
    plan = ForecastPlan(
        metric_label="Monthly volume",
        frequency=ForecastFrequency.MONTH,
        horizon_periods=3,
        historical_series_question="Return monthly volume",
    )
    result = ForecastEngine(backtest_points=4, moving_average_window=3, interval_z=1.96).compute(
        plan, HistoricalTimeSeries(frequency=ForecastFrequency.MONTH, points=points)
    )

    assert len(result.forecast_points) == 3
    assert all(point.predicted >= 0 and point.lower_bound >= 0 for point in result.forecast_points)
    assert all(
        point.lower_bound <= point.predicted <= point.upper_bound
        for point in result.forecast_points
    )
    assert result.forecast_points[0].period == date(2025, 1, 1)


def test_seasonal_candidate_is_excluded_when_training_history_is_too_short() -> None:
    selection = BacktestSelector(4).select(
        tuple(float(value) for value in range(12)),
        (NaiveModel, lambda: SeasonalNaiveModel(12)),
    )
    assert [item.model_name for item in selection.evaluations] == ["naive"]
