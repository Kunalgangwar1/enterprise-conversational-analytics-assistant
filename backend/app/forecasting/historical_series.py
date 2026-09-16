"""Acquire one validated aggregate history through the existing SQL stack."""

import math
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from app.db.query.base import QueryExecutor
from app.db.query.exceptions import QueryError
from app.db.query.models import QueryExecutionResult
from app.forecasting.exceptions import ForecastDataShapeError, ForecastExecutionError
from app.forecasting.models import ForecastPlan, HistoricalTimeSeries, TimeSeriesPoint
from app.nlp2sql.agent import NLP2SQLAgent
from app.nlp2sql.exceptions import NLP2SQLError
from app.nlp2sql.models import SQLValidationDecision
from app.privacy.models import TokenMappingEntry
from app.sql_results.exceptions import SQLResultsError
from app.sql_results.preview import SQLSummaryPreviewBuilder
from app.sql_results.token_resolver import SQLTokenResolver

_TEMPORAL_ALIASES = {"date", "day", "week", "month", "period", "service_date"}
_NUMERIC_ALIASES = {"value", "count", "amount", "total", "metric", "volume"}


@dataclass(frozen=True, slots=True)
class HistoricalSeriesAcquisition:
    """Internal history plus only the protected text allowed at the summary boundary."""

    series: HistoricalTimeSeries
    protected_preview: str
    selected_domains: tuple[str, ...]
    selected_tables: tuple[str, ...]


class HistoricalSeriesService:
    """Generate, validate, token-resolve, and execute one bounded history query."""

    def __init__(
        self,
        nlp2sql_agent: NLP2SQLAgent,
        query_executor: QueryExecutor,
        preview_builder: SQLSummaryPreviewBuilder,
        *,
        max_history_points: int,
        token_resolver: SQLTokenResolver | None = None,
    ) -> None:
        self._nlp2sql_agent = nlp2sql_agent
        self._query_executor = query_executor
        self._preview_builder = preview_builder
        self._maximum = max_history_points
        self._token_resolver = token_resolver or SQLTokenResolver()

    def acquire(
        self,
        plan: ForecastPlan,
        token_mappings: tuple[TokenMappingEntry, ...] = (),
    ) -> HistoricalSeriesAcquisition:
        """Return a typed two-column history without exposing generated SQL."""

        try:
            generated = self._nlp2sql_agent.generate_sql(plan.historical_series_question)
            if (
                generated.validation.decision is not SQLValidationDecision.ACCEPT
                or generated.final_sql is None
            ):
                raise ForecastExecutionError("The historical-series query was not accepted")
            executable_sql = self._token_resolver.resolve(generated.final_sql, token_mappings)
            result = self._query_executor.execute(
                executable_sql,
                max_rows=self._maximum,
            )
            if result.truncated:
                raise ForecastDataShapeError(
                    "Historical query must return the most recent bounded series"
                )
            series = _extract_series(result, plan)
            preview = self._preview_builder.build(result, token_mappings)
        except ForecastExecutionError:
            raise
        except ForecastDataShapeError:
            raise
        except (NLP2SQLError, QueryError, SQLResultsError) as exc:
            raise ForecastExecutionError("Historical forecast data could not be acquired") from exc
        return HistoricalSeriesAcquisition(
            series=series,
            protected_preview=preview,
            selected_domains=generated.selected_domains,
            selected_tables=generated.selected_tables,
        )


def _extract_series(result: QueryExecutionResult, plan: ForecastPlan) -> HistoricalTimeSeries:
    if len(result.columns) != 2:
        raise ForecastDataShapeError(
            "Forecast history must contain exactly one period and one numeric value column"
        )
    if not result.rows:
        return HistoricalTimeSeries(frequency=plan.frequency, points=())

    first, second = result.columns
    temporal = _choose_column(
        result.rows, first, second, parser=_parse_period, aliases=_TEMPORAL_ALIASES
    )
    numeric = _choose_column(
        result.rows, first, second, parser=_parse_number, aliases=_NUMERIC_ALIASES
    )
    if temporal is None or numeric is None or temporal == numeric:
        raise ForecastDataShapeError(
            "Forecast history requires one parseable period column and one finite numeric column"
        )
    try:
        points = tuple(
            TimeSeriesPoint(
                period=_parse_period(row.get(temporal)),
                value=_parse_number(row.get(numeric)),
            )
            for row in result.rows
        )
    except (TypeError, ValueError, InvalidOperation) as exc:
        raise ForecastDataShapeError("Forecast history contains invalid values") from exc
    return HistoricalTimeSeries(frequency=plan.frequency, points=points)


def _choose_column(
    rows: list[dict[str, Any]],
    first: str,
    second: str,
    *,
    parser: Any,
    aliases: set[str],
) -> str | None:
    valid = []
    for column in (first, second):
        try:
            for row in rows:
                parser(row.get(column))
        except (TypeError, ValueError, InvalidOperation):
            continue
        valid.append(column)
    if len(valid) == 1:
        return valid[0]
    alias_matches = [column for column in valid if column.lower() in aliases]
    return alias_matches[0] if len(alias_matches) == 1 else None


def _parse_period(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        text = value.strip()
        try:
            return date.fromisoformat(text)
        except ValueError:
            return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    raise TypeError("Period is not date-like")


def _parse_number(value: Any) -> float:
    if isinstance(value, bool) or value is None:
        raise TypeError("Metric is not numeric")
    if not isinstance(value, (int, float, Decimal, str)):
        raise TypeError("Metric is not numeric")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("Metric must be finite")
    return number
