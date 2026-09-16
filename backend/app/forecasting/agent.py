"""Internal orchestration for aggregate healthcare operations forecasts."""

from collections.abc import Sequence

from app.forecasting.engine import ForecastEngine
from app.forecasting.historical_series import HistoricalSeriesService
from app.forecasting.models import ForecastChartMetadata, ForecastResult
from app.forecasting.planner import ForecastPlanner
from app.forecasting.summarizer import ForecastSummarizer
from app.forecasting.validation import TimeSeriesValidator
from app.privacy.models import TokenMappingEntry

_WARNINGS = (
    "Forecast intervals are approximate and based on historical backtest error.",
    "This is an aggregate operational forecast, not an individual clinical prediction or "
    "medical advice.",
)


class ForecastingAgent:
    """Compose planning, existing SQL retrieval, deterministic computation, and explanation."""

    def __init__(
        self,
        planner: ForecastPlanner,
        historical_series: HistoricalSeriesService,
        validator: TimeSeriesValidator,
        engine: ForecastEngine,
        summarizer: ForecastSummarizer,
    ) -> None:
        self._planner = planner
        self._historical_series = historical_series
        self._validator = validator
        self._engine = engine
        self._summarizer = summarizer

    def forecast(
        self,
        safe_question: str,
        token_mappings: Sequence[TokenMappingEntry] = (),
    ) -> ForecastResult:
        """Forecast a privacy-safe aggregate question; never invoke privacy processing here."""

        plan = self._planner.plan(safe_question)
        acquisition = self._historical_series.acquire(plan, tuple(token_mappings))
        history = self._validator.validate(acquisition.series)
        computation = self._engine.compute(plan, history)
        summary, summary_source = self._summarizer.summarize(
            safe_question=safe_question,
            plan=plan,
            computation=computation,
            protected_preview=acquisition.protected_preview,
        )
        return ForecastResult(
            metric_label=plan.metric_label,
            frequency=plan.frequency,
            horizon_periods=plan.horizon_periods,
            selected_model=computation.selected_model,
            backtest_metrics=computation.backtest_metrics,
            historical_points=history.points,
            forecast_points=computation.forecast_points,
            summary=summary,
            summary_source=summary_source,
            chart=ForecastChartMetadata(title=f"{plan.metric_label} forecast"),
            warnings=_WARNINGS,
        )
