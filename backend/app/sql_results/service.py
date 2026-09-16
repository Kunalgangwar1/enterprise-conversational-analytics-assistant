"""Accepted-SQL execution and result-presentation orchestration."""

import logging
from collections.abc import Sequence

from app.db.query.base import QueryExecutor
from app.nlp2sql.models import SQLValidationDecision
from app.privacy.models import TokenMappingEntry
from app.sql_results.chart import ChartMetadataBuilder
from app.sql_results.exceptions import SQLNotValidatedError
from app.sql_results.models import SQLAnalyticsResult
from app.sql_results.summarizer import SQLResultSummarizer
from app.sql_results.token_resolver import SQLTokenResolver

logger = logging.getLogger(__name__)


class SQLExecutionService:
    """Execute only accepted SQL and produce a bounded UI-neutral result."""

    def __init__(
        self,
        query_executor: QueryExecutor,
        token_resolver: SQLTokenResolver,
        summarizer: SQLResultSummarizer,
        chart_builder: ChartMetadataBuilder,
    ) -> None:
        self._query_executor = query_executor
        self._token_resolver = token_resolver
        self._summarizer = summarizer
        self._chart_builder = chart_builder

    def execute(
        self,
        *,
        final_sql: str | None,
        decision: SQLValidationDecision,
        token_mappings: Sequence[TokenMappingEntry] = (),
        safe_question: str | None = None,
    ) -> SQLAnalyticsResult:
        if decision is not SQLValidationDecision.ACCEPT or not final_sql or not final_sql.strip():
            raise SQLNotValidatedError("Accepted final SQL is required for execution")

        executable_sql = self._token_resolver.resolve(final_sql, token_mappings)
        query_result = self._query_executor.execute(executable_sql)
        summary, summary_source = self._summarizer.summarize(
            query_result,
            token_mappings,
            safe_question=safe_question,
        )
        chart = self._chart_builder.build(query_result)
        logger.info(
            "SQL analytics query completed",
            extra={
                "row_count": query_result.row_count,
                "elapsed_ms": query_result.elapsed_ms,
                "truncated": query_result.truncated,
            },
        )
        return SQLAnalyticsResult(
            columns=query_result.columns,
            rows=query_result.rows,
            row_count=query_result.row_count,
            truncated=query_result.truncated,
            execution_elapsed_ms=query_result.elapsed_ms,
            summary=summary,
            summary_source=summary_source,
            chart=chart,
        )
