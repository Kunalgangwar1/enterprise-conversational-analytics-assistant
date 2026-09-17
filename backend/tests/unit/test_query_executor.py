"""Unit tests for bounded PostgreSQL query execution and error translation."""

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, call

import pytest
from sqlalchemy import Engine
from sqlalchemy.exc import DBAPIError, OperationalError, SQLAlchemyError, TimeoutError
from sqlalchemy.sql.elements import TextClause

from app.db.query.exceptions import (
    QueryDependencyUnavailableError,
    QueryExecutionError,
    QueryPermissionError,
    QueryPoolTimeoutError,
    QueryTimeoutError,
)
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


def test_executor_uses_bound_parameters_without_changing_unparameterized_path() -> None:
    engine, connection, result = _engine_with_query_result([], ["value"])
    connection.exec_driver_sql.side_effect = [None, None]
    connection.execute.return_value = result
    executor = PostgresQueryExecutor(engine, max_rows=2, timeout_ms=100)

    executor.execute(
        "SELECT 1 AS value WHERE CAST(:start_date AS date) <= CURRENT_DATE",
        parameters={"start_date": date(2025, 1, 1)},
    )

    statement, parameters = connection.execute.call_args.args
    assert isinstance(statement, TextClause)
    assert str(statement).endswith("CAST(:start_date AS date) <= CURRENT_DATE")
    assert parameters == {"start_date": date(2025, 1, 1)}


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


def test_pool_exhaustion_is_bounded_and_sanitized_without_retry() -> None:
    engine = MagicMock(spec=Engine)
    raw_error = TimeoutError("QueuePool limit reached for postgresql://user:secret@host/db")
    engine.connect.side_effect = raw_error
    executor = PostgresQueryExecutor(engine, max_rows=5, timeout_ms=100)

    with pytest.raises(QueryPoolTimeoutError) as captured:
        executor.execute("SELECT 1")

    assert "secret" not in str(captured.value)
    engine.connect.assert_called_once_with()


def test_connection_outage_is_safe_and_not_retried() -> None:
    engine = MagicMock(spec=Engine)
    raw_error = OperationalError(
        "SELECT 1",
        None,
        OSError("postgresql://user:secret@internal/db refused"),
        connection_invalidated=True,
    )
    engine.connect.side_effect = raw_error
    executor = PostgresQueryExecutor(engine, max_rows=5, timeout_ms=100)

    with pytest.raises(QueryDependencyUnavailableError) as captured:
        executor.execute("SELECT 1")

    assert "secret" not in str(captured.value)
    engine.connect.assert_called_once_with()


def test_read_role_permission_failure_is_sanitized() -> None:
    class InsufficientPrivilege(Exception):
        sqlstate = "42501"

    engine, connection, _ = _engine_with_query_result([], [])
    raw_error = DBAPIError(
        "SELECT private_column",
        None,
        InsufficientPrivilege("permission denied for private table"),
        False,
    )
    connection.exec_driver_sql.side_effect = [None, None, raw_error]
    executor = PostgresQueryExecutor(engine, max_rows=5, timeout_ms=100)

    with pytest.raises(QueryPermissionError) as captured:
        executor.execute("SELECT private_column FROM restricted_table")

    assert "private" not in str(captured.value)


def test_failed_transaction_context_rolls_back_and_connection_is_released() -> None:
    engine, connection, _ = _engine_with_query_result([], [])
    raw_error = SQLAlchemyError("synthetic execution failure")
    connection.exec_driver_sql.side_effect = [None, None, raw_error]
    executor = PostgresQueryExecutor(engine, max_rows=5, timeout_ms=100)

    with pytest.raises(QueryExecutionError):
        executor.execute("SELECT 1")

    transaction_exit = connection.begin.return_value.__exit__
    connection_exit = engine.connect.return_value.__exit__
    assert transaction_exit.call_args.args[0] is SQLAlchemyError
    assert connection_exit.called


def test_executor_close_disposes_pool() -> None:
    engine = MagicMock(spec=Engine)
    executor = PostgresQueryExecutor(engine, max_rows=5, timeout_ms=100)

    executor.close()

    engine.dispose.assert_called_once_with()


def test_executor_recovers_on_later_call_after_database_returns() -> None:
    engine = MagicMock(spec=Engine)
    raw_error = OperationalError(
        "SELECT 1",
        None,
        OSError("synthetic connection refused"),
        connection_invalidated=True,
    )
    successful_context = MagicMock()
    connection = successful_context.__enter__.return_value
    result = MagicMock()
    result.keys.return_value = ["value"]
    result.mappings.return_value.fetchmany.return_value = [{"value": 1}]
    connection.exec_driver_sql.side_effect = [None, None, result]
    engine.connect.side_effect = [raw_error, successful_context]
    executor = PostgresQueryExecutor(engine, max_rows=2, timeout_ms=100)

    with pytest.raises(QueryDependencyUnavailableError):
        executor.execute("SELECT 1 AS value")

    recovered = executor.execute("SELECT 1 AS value")
    assert recovered.rows == [{"value": 1}]
    assert engine.connect.call_count == 2
