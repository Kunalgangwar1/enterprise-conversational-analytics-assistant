"""Application construction for Phase 13 SQL execution services."""

from functools import partial

from app.core.config import Settings
from app.db.query.factory import build_query_executor
from app.llm.factory import create_llm_client
from app.sql_results.chart import ChartMetadataBuilder
from app.sql_results.preview import SQLSummaryPreviewBuilder
from app.sql_results.service import SQLExecutionService
from app.sql_results.summarizer import SQLResultSummarizer
from app.sql_results.token_resolver import SQLTokenResolver


def build_sql_execution_service(settings: Settings) -> SQLExecutionService:
    """Build database execution eagerly while keeping LLM construction lazy."""

    preview_builder = SQLSummaryPreviewBuilder(
        max_rows=settings.sql_result_summary_max_rows,
        max_chars=settings.sql_result_summary_max_chars,
    )
    return SQLExecutionService(
        build_query_executor(settings),
        SQLTokenResolver(),
        SQLResultSummarizer(partial(create_llm_client, settings), preview_builder),
        ChartMetadataBuilder(),
    )
