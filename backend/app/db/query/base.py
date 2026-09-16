"""Database-independent query executor contract."""

from typing import Protocol, runtime_checkable

from app.db.query.models import QueryExecutionResult


@runtime_checkable
class QueryExecutor(Protocol):
    """Execute a validated analytical query and return a bounded result."""

    def execute(
        self,
        sql: str,
        *,
        max_rows: int | None = None,
        timeout_ms: int | None = None,
    ) -> QueryExecutionResult:
        """Execute one read-only SQL statement with optional stricter limits."""
        ...
