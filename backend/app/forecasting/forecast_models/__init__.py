"""Dependency-free deterministic forecasting models."""

from app.forecasting.forecast_models.base import ForecastModel
from app.forecasting.forecast_models.linear_trend import LinearTrendModel
from app.forecasting.forecast_models.moving_average import MovingAverageModel
from app.forecasting.forecast_models.naive import NaiveModel
from app.forecasting.forecast_models.seasonal_naive import SeasonalNaiveModel

__all__ = [
    "ForecastModel",
    "LinearTrendModel",
    "MovingAverageModel",
    "NaiveModel",
    "SeasonalNaiveModel",
]
