"""Deterministic validation for historical time-series inputs."""

from collections.abc import Callable
from datetime import date

from app.forecasting.exceptions import InsufficientHistoryError, IrregularTimeSeriesError
from app.forecasting.models import HistoricalTimeSeries
from app.forecasting.periods import next_period


class TimeSeriesValidator:
    """Require bounded, unique, regular, completed historical periods."""

    def __init__(
        self,
        *,
        min_history_points: int,
        max_history_points: int,
        today: Callable[[], date] = date.today,
    ) -> None:
        self._minimum = min_history_points
        self._maximum = max_history_points
        self._today = today

    def validate(self, series: HistoricalTimeSeries) -> HistoricalTimeSeries:
        """Sort and validate a series; missing periods are never imputed."""

        points = sorted(series.points, key=lambda point: point.period)
        if len(points) < self._minimum:
            raise InsufficientHistoryError(
                f"At least {self._minimum} historical periods are required"
            )
        if len({point.period for point in points}) != len(points):
            raise IrregularTimeSeriesError("Historical periods must be unique")
        today = self._today()
        if any(next_period(point.period, series.frequency) > today for point in points):
            raise IrregularTimeSeriesError(
                "Historical data must contain only completed, non-future periods"
            )
        points = points[-self._maximum :]
        for previous, current in zip(points, points[1:], strict=False):
            if next_period(previous.period, series.frequency) != current.period:
                raise IrregularTimeSeriesError(
                    "Historical periods must be complete and exactly regular"
                )
        return HistoricalTimeSeries(frequency=series.frequency, points=tuple(points))
