"""Deterministic Phase 13 service fixtures."""

from collections.abc import Callable

from app.db.query.models import QueryExecutionResult
from app.llm.base import LLMClient
from app.sql_results import (
    ChartMetadataBuilder,
    SQLExecutionService,
    SQLResultSummarizer,
    SQLTokenResolver,
)
from app.sql_results.preview import SQLSummaryPreviewBuilder


class RecordingQueryExecutor:
    """Small query executor fake that records only test SQL."""

    def __init__(self, result: QueryExecutionResult) -> None:
        self.result = result
        self.calls: list[str] = []

    def execute(self, sql: str) -> QueryExecutionResult:
        self.calls.append(sql)
        return self.result


def execution_service(
    executor: RecordingQueryExecutor,
    llm_client_factory: Callable[[], LLMClient],
    *,
    max_summary_rows: int = 50,
    max_summary_chars: int = 12_000,
) -> SQLExecutionService:
    """Build a real service around deterministic fakes."""

    return SQLExecutionService(
        executor,
        SQLTokenResolver(),
        SQLResultSummarizer(
            llm_client_factory,
            SQLSummaryPreviewBuilder(
                max_rows=max_summary_rows,
                max_chars=max_summary_chars,
            ),
        ),
        ChartMetadataBuilder(),
    )
