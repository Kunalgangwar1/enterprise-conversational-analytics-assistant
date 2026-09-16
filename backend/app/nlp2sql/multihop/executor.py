"""Stricter per-hop wrapper over the existing read-only QueryExecutor."""

from app.db.query.base import QueryExecutor
from app.db.query.models import QueryExecutionResult
from app.nlp2sql.multihop.budget import HopAllowance


class BudgetedQueryExecutor:
    """Delegate to one existing executor and defensively enforce returned rows."""

    def __init__(self, query_executor: QueryExecutor) -> None:
        self._query_executor = query_executor

    def execute(self, sql: str, allowance: HopAllowance) -> QueryExecutionResult:
        result = self._query_executor.execute(
            sql,
            max_rows=allowance.max_rows,
            timeout_ms=allowance.timeout_ms,
        )
        rows = result.rows[: allowance.max_rows]
        was_trimmed = len(result.rows) > len(rows) or result.row_count > len(rows)
        return QueryExecutionResult(
            columns=result.columns,
            rows=rows,
            row_count=len(rows),
            truncated=result.truncated or was_trimmed,
            elapsed_ms=result.elapsed_ms,
        )
