"""Unit tests for bounded PostgreSQL query execution and error translation."""

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, call

import pytest
from sqlalchemy import Engine
from sqlalchemy.exc import DBAPIError, SQLAlchemyError

from app.db.query.exceptions import QueryExecutionError, QueryTimeoutError
from app.db.query.postgres import PostgresQueryExecutor


def _engine_with_query_result(
    rows: list[dict[str, object]], columns: list[str]
) -> tuple[MagicMock, MagicMock, MagicMock]:
    engine = MagicMock(spec=Engine)
    connection = engine.connect.return_value.__enter__.return_value
    result = MagicMock()
    result.keys.return_value = columns
    result.mappings.return_value.fetchmany.return_value = rows
    connection.exec_driver_sql.side_effect = [None, None, result]
    return engine, connection, result


def test_executor_converts_rows_and_enforces_truncation() -> None:
    rows = [
        {"amount": Decimal("12.34"), "service_date": date(2025, 1, 1)},
        {"amount": Decimal("56.78"), "service_date": date(2025, 1, 2)},
        {"amount": Decimal("90.12"), "service_date": date(2025, 1, 3)},
    ]
    engine, connection, result = _engine_with_query_result(rows, ["amount", "service_date"])
    executor = PostgresQueryExecutor(engine, max_rows=2, timeout_ms=123)

    query_result = executor.execute("SELECT amount, service_date FROM claims")

    assert query_result.columns == ["amount", "service_date"]
    assert query_result.rows == rows[:2]
    assert isinstance(query_result.rows[0]["amount"], Decimal)
    assert isinstance(query_result.rows[0]["service_date"], date)
    assert query_result.row_count == 2
    assert query_result.truncated is True
    assert query_result.elapsed_ms >= 0
    assert connection.exec_driver_sql.call_args_list == [
        call("SET TRANSACTION READ ONLY"),
        call("SET LOCAL statement_timeout = 123"),
        call("SELECT amount, service_date FROM claims"),
    ]
    result.mappings.return_value.fetchmany.assert_called_once_with(3)


def test_executor_reports_untruncated_short_results() -> None:
    engine, _, _ = _engine_with_query_result([{"value": 1}], ["value"])
    executor = PostgresQueryExecutor(engine, max_rows=2, timeout_ms=100)

    query_result = executor.execute("SELECT 1 AS value")

    assert query_result.rows == [{"value": 1}]
    assert query_result.row_count == 1
    assert query_result.truncated is False


def test_per_call_limits_can_only_tighten_configured_limits() -> None:
    rows = [{"value": index} for index in range(4)]
    engine, connection, result = _engine_with_query_result(rows, ["value"])
    executor = PostgresQueryExecutor(engine, max_rows=10, timeout_ms=500)

    query_result = executor.execute("SELECT value", max_rows=3, timeout_ms=200)

    assert query_result.row_count == 3
    assert query_result.truncated is True
    assert connection.exec_driver_sql.call_args_list[:2] == [
        call("SET TRANSACTION READ ONLY"),
        call("SET LOCAL statement_timeout = 200"),
    ]
    result.mappings.return_value.fetchmany.assert_called_once_with(4)


def test_per_call_limits_cannot_weaken_configured_limits() -> None:
    engine, connection, result = _engine_with_query_result([{"value": 1}], ["value"])
    executor = PostgresQueryExecutor(engine, max_rows=2, timeout_ms=100)

    executor.execute("SELECT value", max_rows=50, timeout_ms=5_000)

    assert connection.exec_driver_sql.call_args_list[:2] == [
        call("SET TRANSACTION READ ONLY"),
        call("SET LOCAL statement_timeout = 100"),
    ]
    result.mappings.return_value.fetchmany.assert_called_once_with(3)


def test_statement_timeout_is_translated_without_raw_details() -> None:
    class OriginalTimeoutError(Exception):
        sqlstate = "57014"

    engine, connection, _ = _engine_with_query_result([], [])
    raw_error = DBAPIError(
        "SELECT pg_sleep(10)",
        None,
        OriginalTimeoutError("database host and credential details"),
        False,
    )
    connection.exec_driver_sql.side_effect = [None, None, raw_error]
    executor = PostgresQueryExecutor(engine, max_rows=5, timeout_ms=10)

    with pytest.raises(QueryTimeoutError, match="configured execution timeout") as captured:
        executor.execute("SELECT pg_sleep(10)")

    assert "credential" not in str(captured.value)
    assert captured.value.__cause__ is raw_error


def test_generic_database_error_is_sanitized_and_chained() -> None:
    engine, connection, _ = _engine_with_query_result([], [])
    raw_error = SQLAlchemyError("postgresql://user:secret@example.internal/database")
    connection.exec_driver_sql.side_effect = [None, None, raw_error]
    executor = PostgresQueryExecutor(engine, max_rows=5, timeout_ms=100)

    with pytest.raises(QueryExecutionError, match="could not be executed") as captured:
        executor.execute("SELECT 1")

    assert "secret" not in str(captured.value)
    assert captured.value.__cause__ is raw_error
