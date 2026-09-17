"""PostgreSQL implementation of the safe query executor contract."""

from collections.abc import Mapping
from time import perf_counter

from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError, SQLAlchemyError

from app.db.query.exceptions import (
    QueryConfigurationError,
    QueryExecutionError,
    QueryTimeoutError,
)
from app.db.query.guard import validate_read_only_sql
from app.db.query.models import QueryExecutionResult
from app.observability.metrics import ApplicationMetrics, get_metrics
from app.observability.tracing import start_span

_POSTGRES_QUERY_CANCELED_SQLSTATE = "57014"


def _is_statement_timeout(error: DBAPIError) -> bool:
    original_error = error.orig
    return getattr(original_error, "sqlstate", None) == _POSTGRES_QUERY_CANCELED_SQLSTATE


class PostgresQueryExecutor:
    """Execute bounded SELECT queries within read-only PostgreSQL transactions."""

    def __init__(self, engine: Engine, *, max_rows: int, timeout_ms: int) -> None:
        if max_rows < 1:
            raise QueryConfigurationError("Query row limit must be at least 1.")
        if timeout_ms < 1:
            raise QueryConfigurationError("Query timeout must be at least 1 millisecond.")
        self._engine = engine
        self._max_rows = max_rows
        self._timeout_ms = timeout_ms

    def execute(
        self,
        sql: str,
        *,
        parameters: Mapping[str, object] | None = None,
        max_rows: int | None = None,
        timeout_ms: int | None = None,
    ) -> QueryExecutionResult:
        """Validate and execute one read-only query with bounded fetching."""
        effective_max_rows = self._strict_limit(max_rows, self._max_rows, "row limit")
        effective_timeout_ms = self._strict_limit(timeout_ms, self._timeout_ms, "timeout")
        metrics = get_metrics()
        with start_span("sql.validate", {"operation.name": "validate"}) as validation_span:
            try:
                validate_read_only_sql(sql)
            except Exception:
                metrics.record("sql.validation.decision", 1, {"validation_decision": "reject"})
                validation_span.set_attribute("outcome", "error")
                raise
            metrics.record("sql.validation.decision", 1, {"validation_decision": "accept"})
            validation_span.set_attribute("outcome", "success")
        started_at = perf_counter()

        with start_span(
            "db.query",
            {
                "db.system": "postgresql",
                "db.operation.name": "SELECT",
                "db.query.timeout_ms": effective_timeout_ms,
            },
        ) as span:
            try:
                with self._engine.connect() as connection, connection.begin():
                    connection.exec_driver_sql("SET TRANSACTION READ ONLY")
                    # The value is a constructor-validated integer, never SQL input.
                    connection.exec_driver_sql(
                        f"SET LOCAL statement_timeout = {effective_timeout_ms}"
                    )
                    result = (
                        connection.execute(text(sql), dict(parameters))
                        if parameters is not None
                        else connection.exec_driver_sql(sql)
                    )
                    columns = list(result.keys())
                    fetched_rows = result.mappings().fetchmany(effective_max_rows + 1)
            except DBAPIError as exc:
                outcome = "timeout" if _is_statement_timeout(exc) else "error"
                self._record_error(metrics, started_at, outcome)
                if outcome == "timeout":
                    raise QueryTimeoutError(
                        "The query exceeded the configured execution timeout."
                    ) from exc
                raise QueryExecutionError("The query could not be executed.") from exc
            except SQLAlchemyError as exc:
                self._record_error(metrics, started_at, "error")
                raise QueryExecutionError("The query could not be executed.") from exc

            truncated = len(fetched_rows) > effective_max_rows
            rows = [dict(row) for row in fetched_rows[:effective_max_rows]]
            elapsed = perf_counter() - started_at
            outcome = "truncated" if truncated else "success"
            metrics.record("sql.execution.duration", elapsed, {"outcome": outcome})
            metrics.record("sql.execution.rows", len(rows), {"outcome": outcome})
            if truncated:
                metrics.record("sql.execution.truncated", 1, {"outcome": "truncated"})
            span.set_attribute("db.response.returned_rows", len(rows))
            span.set_attribute("db.query.truncated", truncated)
            span.set_attribute("outcome", outcome)
            return QueryExecutionResult(
                columns=columns,
                rows=rows,
                row_count=len(rows),
                truncated=truncated,
                elapsed_ms=elapsed * 1_000,
            )

    @staticmethod
    def _record_error(metrics: ApplicationMetrics, started_at: float, outcome: str) -> None:
        metrics.record("sql.execution.duration", perf_counter() - started_at, {"outcome": outcome})
        metrics.record("sql.execution.errors", 1, {"outcome": outcome})

    @staticmethod
    def _strict_limit(requested: int | None, configured: int, name: str) -> int:
        if requested is None:
            return configured
        if requested < 1:
            raise QueryConfigurationError(f"Query {name} override must be at least 1.")
        return min(requested, configured)
