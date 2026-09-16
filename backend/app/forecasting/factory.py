"""Composition helpers for the internal forecasting workflow."""

from app.core.config import Settings
from app.db.query.base import QueryExecutor
from app.forecasting.agent import ForecastingAgent
from app.forecasting.engine import ForecastEngine
from app.forecasting.historical_series import HistoricalSeriesService
from app.forecasting.planner import ForecastPlanner
from app.forecasting.summarizer import ForecastSummarizer
from app.forecasting.validation import TimeSeriesValidator
from app.llm.base import LLMClient
from app.nlp2sql.agent import NLP2SQLAgent
from app.sql_results.preview import SQLSummaryPreviewBuilder


def build_forecasting_agent(
    settings: Settings,
    llm_client: LLMClient,
    nlp2sql_agent: NLP2SQLAgent,
    query_executor: QueryExecutor,
) -> ForecastingAgent:
    """Build forecasting from injected standard SQL and provider abstractions."""

    preview_builder = SQLSummaryPreviewBuilder(
        max_rows=settings.sql_result_summary_max_rows,
        max_chars=settings.sql_result_summary_max_chars,
    )
    return ForecastingAgent(
        ForecastPlanner(
            llm_client,
            default_horizon=settings.forecast_default_horizon,
            max_horizon=settings.forecast_max_horizon,
            max_history_points=settings.forecast_max_history_points,
        ),
        HistoricalSeriesService(
            nlp2sql_agent,
            query_executor,
            preview_builder,
            max_history_points=settings.forecast_max_history_points,
        ),
        TimeSeriesValidator(
            min_history_points=settings.forecast_min_history_points,
            max_history_points=settings.forecast_max_history_points,
        ),
        ForecastEngine(
            backtest_points=settings.forecast_backtest_points,
            moving_average_window=settings.forecast_moving_average_window,
            interval_z=settings.forecast_interval_z,
        ),
        ForecastSummarizer(llm_client),
    )
