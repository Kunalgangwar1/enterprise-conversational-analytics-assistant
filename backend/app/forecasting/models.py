"""Typed forecasting plans, numerical results, and presentation metadata."""

from datetime import date
from enum import StrEnum
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.sql_results.models import ChartType, SummarySource

NonBlankString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
FiniteFloat = Annotated[float, Field(allow_inf_nan=False)]


class ForecastModelValue(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ForecastFrequency(StrEnum):
    DAY = "day"
    WEEK = "week"
    MONTH = "month"


class ForecastPlanDraft(ForecastModelValue):
    metric_label: NonBlankString
    frequency: ForecastFrequency
    horizon_periods: int | None = Field(default=None, ge=1)
    historical_series_question: NonBlankString
    description: str | None = None
    filters_description: str | None = None


class ForecastPlan(ForecastModelValue):
    metric_label: NonBlankString
    frequency: ForecastFrequency
    horizon_periods: int = Field(ge=1)
    historical_series_question: NonBlankString
    description: str | None = None
    filters_description: str | None = None


class TimeSeriesPoint(ForecastModelValue):
    period: date
    value: FiniteFloat


class HistoricalTimeSeries(ForecastModelValue):
    frequency: ForecastFrequency
    points: tuple[TimeSeriesPoint, ...]


class ForecastMetrics(ForecastModelValue):
    mae: FiniteFloat = Field(ge=0)
    rmse: FiniteFloat = Field(ge=0)
    smape: FiniteFloat = Field(ge=0)


class ModelEvaluation(ForecastModelValue):
    model_name: NonBlankString
    metrics: ForecastMetrics


class ForecastPoint(ForecastModelValue):
    period: date
    predicted: FiniteFloat
    lower_bound: FiniteFloat
    upper_bound: FiniteFloat

    @model_validator(mode="after")
    def require_ordered_bounds(self) -> Self:
        if not self.lower_bound <= self.predicted <= self.upper_bound:
            raise ValueError("forecast bounds must contain the prediction")
        return self


class ForecastComputation(ForecastModelValue):
    selected_model: NonBlankString
    backtest_metrics: ForecastMetrics
    forecast_points: tuple[ForecastPoint, ...]
    evaluations: tuple[ModelEvaluation, ...]


class ForecastSummary(ForecastModelValue):
    summary: NonBlankString


class ForecastChartMetadata(ForecastModelValue):
    chart_type: ChartType = ChartType.LINE
    x_axis: str = "period"
    series: tuple[str, ...] = (
        "historical",
        "forecast",
        "lower_bound",
        "upper_bound",
    )
    title: NonBlankString


class ForecastResult(ForecastModelValue):
    metric_label: NonBlankString
    frequency: ForecastFrequency
    horizon_periods: int = Field(ge=1)
    selected_model: NonBlankString
    backtest_metrics: ForecastMetrics
    historical_points: tuple[TimeSeriesPoint, ...]
    forecast_points: tuple[ForecastPoint, ...]
    summary: NonBlankString
    summary_source: SummarySource
    chart: ForecastChartMetadata
    warnings: tuple[NonBlankString, ...] = ()
