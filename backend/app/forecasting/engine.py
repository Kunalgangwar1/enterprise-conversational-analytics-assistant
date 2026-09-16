"""Deterministic forecast computation independent of all LLM providers."""

from app.forecasting.backtest import BacktestSelector, ModelFactory
from app.forecasting.forecast_models import (
    LinearTrendModel,
    MovingAverageModel,
    NaiveModel,
    SeasonalNaiveModel,
)
from app.forecasting.intervals import build_forecast_points
from app.forecasting.models import (
    ForecastComputation,
    ForecastFrequency,
    ForecastPlan,
    HistoricalTimeSeries,
)

_SEASON_LENGTHS = {
    ForecastFrequency.DAY: 7,
    ForecastFrequency.WEEK: 52,
    ForecastFrequency.MONTH: 12,
}


class ForecastEngine:
    """Backtest candidates, refit the winner, and project a bounded horizon."""

    def __init__(
        self,
        *,
        backtest_points: int,
        moving_average_window: int,
        interval_z: float,
    ) -> None:
        self._selector = BacktestSelector(backtest_points)
        self._window = moving_average_window
        self._interval_z = interval_z

    def compute(
        self,
        plan: ForecastPlan,
        history: HistoricalTimeSeries,
    ) -> ForecastComputation:
        values = tuple(point.value for point in history.points)
        factories = self._factories(plan.frequency)
        selection = self._selector.select(values, factories)
        model = selection.factory()
        model.fit(values)
        predictions = model.predict(plan.horizon_periods)
        nonnegative = all(value >= 0 for value in values)
        points = build_forecast_points(
            predictions,
            latest_period=history.points[-1].period,
            frequency=plan.frequency,
            rmse=selection.evaluation.metrics.rmse,
            interval_z=self._interval_z,
            nonnegative=nonnegative,
        )
        return ForecastComputation(
            selected_model=model.name,
            backtest_metrics=selection.evaluation.metrics,
            forecast_points=points,
            evaluations=selection.evaluations,
        )

    def _factories(self, frequency: ForecastFrequency) -> tuple[ModelFactory, ...]:
        season_length = _SEASON_LENGTHS[frequency]
        factories: tuple[ModelFactory, ...] = (
            NaiveModel,
            lambda: MovingAverageModel(self._window),
            LinearTrendModel,
            lambda: SeasonalNaiveModel(season_length),
        )
        return factories
