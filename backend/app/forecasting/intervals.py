"""Approximate forecast intervals derived from holdout RMSE."""

import math
from datetime import date

from app.forecasting.models import ForecastFrequency, ForecastPoint
from app.forecasting.periods import next_period


def build_forecast_points(
    predictions: tuple[float, ...],
    *,
    latest_period: date,
    frequency: ForecastFrequency,
    rmse: float,
    interval_z: float,
    nonnegative: bool,
) -> tuple[ForecastPoint, ...]:
    """Pair predictions with future periods and widening approximate intervals."""

    result: list[ForecastPoint] = []
    period = latest_period
    for step, raw_prediction in enumerate(predictions, start=1):
        period = next_period(period, frequency)
        predicted = max(0.0, raw_prediction) if nonnegative else raw_prediction
        margin = interval_z * rmse * math.sqrt(step)
        lower = predicted - margin
        if nonnegative:
            lower = max(0.0, lower)
        result.append(
            ForecastPoint(
                period=period,
                predicted=predicted,
                lower_bound=lower,
                upper_bound=predicted + margin,
            )
        )
    return tuple(result)
