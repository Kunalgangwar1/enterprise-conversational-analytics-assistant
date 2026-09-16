"""Historical SQL result extraction and regularity validation tests."""

from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.db.query.models import QueryExecutionResult
from app.forecasting.exceptions import (
    ForecastDataShapeError,
    ForecastExecutionError,
    InsufficientHistoryError,
    IrregularTimeSeriesError,
)
from app.forecasting.historical_series import HistoricalSeriesService
from app.forecasting.models import (
    ForecastFrequency,
    ForecastPlan,
    HistoricalTimeSeries,
    TimeSeriesPoint,
)
from app.forecasting.validation import TimeSeriesValidator
from app.nlp2sql.models import SQLValidationDecision, SQLValidationResult
from app.sql_results.preview import SQLSummaryPreviewBuilder


def _plan(frequency: ForecastFrequency = ForecastFrequency.DAY) -> ForecastPlan:
    return ForecastPlan(
        metric_label="Claim volume",
        frequency=frequency,
        horizon_periods=3,
        historical_series_question="Return daily aggregate claim counts",
    )


def _service(result: QueryExecutionResult) -> tuple[HistoricalSeriesService, MagicMock]:
    generated = SimpleNamespace(
        validation=SQLValidationResult(decision=SQLValidationDecision.ACCEPT, score=1, attempt=1),
        final_sql="SELECT period, value FROM safe_history",
        selected_domains=("claims",),
        selected_tables=("claims",),
    )
    nlp2sql = MagicMock()
    nlp2sql.generate_sql.return_value = generated
    executor = MagicMock()
    executor.execute.return_value = result
    return (
        HistoricalSeriesService(
            nlp2sql,
            executor,
            SQLSummaryPreviewBuilder(max_rows=10, max_chars=2000),
            max_history_points=120,
        ),
        executor,
    )


def test_history_reuses_accepted_sql_executor_with_stricter_row_bound() -> None:
    result = QueryExecutionResult(
        columns=["period", "value"],
        rows=[{"period": "2025-01-01", "value": "2.5"}],
        row_count=1,
        truncated=False,
        elapsed_ms=1,
    )
    service, executor = _service(result)

    acquired = service.acquire(_plan())

    assert acquired.series.points[0].value == 2.5
    assert acquired.selected_tables == ("claims",)
    executor.execute.assert_called_once_with("SELECT period, value FROM safe_history", max_rows=120)


def test_history_cannot_bypass_phase_12_acceptance() -> None:
    result = QueryExecutionResult(
        columns=["period", "value"], rows=[], row_count=0, truncated=False, elapsed_ms=1
    )
    service, executor = _service(result)
    service._nlp2sql_agent.generate_sql.return_value.validation = SQLValidationResult(  # noqa: SLF001
        decision=SQLValidationDecision.REJECT,
        score=0,
        attempt=1,
    )

    with pytest.raises(ForecastExecutionError):
        service.acquire(_plan())
    executor.execute.assert_not_called()


def test_history_rejects_executor_truncation_instead_of_using_oldest_rows() -> None:
    result = QueryExecutionResult(
        columns=["period", "value"],
        rows=[{"period": "2025-01-01", "value": 1}],
        row_count=1,
        truncated=True,
        elapsed_ms=1,
    )
    service, _ = _service(result)
    with pytest.raises(ForecastDataShapeError, match="most recent bounded"):
        service.acquire(_plan())


@pytest.mark.parametrize(
    "result",
    [
        QueryExecutionResult(
            columns=["period", "value", "extra"],
            rows=[{"period": "2025-01-01", "value": 1, "extra": 2}],
            row_count=1,
            truncated=False,
            elapsed_ms=1,
        ),
        QueryExecutionResult(
            columns=["period", "value"],
            rows=[{"period": "not-a-date", "value": 1}],
            row_count=1,
            truncated=False,
            elapsed_ms=1,
        ),
        QueryExecutionResult(
            columns=["period", "value"],
            rows=[{"period": "2025-01-01", "value": float("inf")}],
            row_count=1,
            truncated=False,
            elapsed_ms=1,
        ),
    ],
)
def test_history_rejects_invalid_shape_or_values(result: QueryExecutionResult) -> None:
    service, _ = _service(result)
    with pytest.raises(ForecastDataShapeError):
        service.acquire(_plan())


def _series(periods: list[date]) -> HistoricalTimeSeries:
    return HistoricalTimeSeries(
        frequency=ForecastFrequency.DAY,
        points=tuple(
            TimeSeriesPoint(period=period, value=float(index))
            for index, period in enumerate(periods)
        ),
    )


def _validator(minimum: int = 4, maximum: int = 10) -> TimeSeriesValidator:
    return TimeSeriesValidator(
        min_history_points=minimum,
        max_history_points=maximum,
        today=lambda: date(2025, 2, 1),
    )


def test_validator_sorts_and_keeps_latest_bounded_regular_history() -> None:
    periods = [date(2025, 1, 1) + timedelta(days=index) for index in range(12)]
    validated = _validator(maximum=8).validate(_series(list(reversed(periods))))
    assert len(validated.points) == 8
    assert validated.points[0].period == date(2025, 1, 5)


def test_validator_rejects_insufficient_duplicate_missing_and_incomplete_history() -> None:
    base = date(2025, 1, 1)
    with pytest.raises(InsufficientHistoryError):
        _validator().validate(_series([base, base + timedelta(days=1)]))
    with pytest.raises(IrregularTimeSeriesError):
        _validator().validate(
            _series([base, base, base + timedelta(days=1), base + timedelta(days=2)])
        )
    with pytest.raises(IrregularTimeSeriesError):
        _validator().validate(
            _series(
                [
                    base,
                    base + timedelta(days=1),
                    base + timedelta(days=3),
                    base + timedelta(days=4),
                ]
            )
        )
    future = date(2025, 1, 30)
    with pytest.raises(IrregularTimeSeriesError):
        _validator().validate(_series([future + timedelta(days=index) for index in range(4)]))
