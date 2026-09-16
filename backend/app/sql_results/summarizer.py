"""Privacy-safe LLM result summarization with deterministic fallbacks."""

from collections.abc import Callable, Sequence

from pydantic import ValidationError

from app.db.query.models import QueryExecutionResult
from app.llm.base import LLMClient
from app.llm.exceptions import LLMError
from app.llm.models import LLMMessage, LLMRequest, LLMRole
from app.privacy.exceptions import PrivacyUnmaskingError
from app.privacy.models import TokenMappingEntry
from app.privacy.unmasker import ResponseUnmasker
from app.sql_results.models import SQLResultSummary, SummarySource
from app.sql_results.preview import SQLSummaryPreviewBuilder

SQL_RESULT_SUMMARY_SYSTEM_PROMPT = """Summarize only the supplied bounded query result in concise,
business-friendly language. Do not invent missing rows or infer data not shown. Respect the
truncated flag and do not imply the preview or returned rows are complete when it is true. Do not
claim statistical significance, reveal protected placeholders, output SQL, or provide hidden
reasoning. Return only the requested structured summary."""


class SQLResultSummarizer:
    """Summarize protected previews while preserving successful database results."""

    def __init__(
        self,
        llm_client_factory: Callable[[], LLMClient],
        preview_builder: SQLSummaryPreviewBuilder,
    ) -> None:
        self._llm_client_factory = llm_client_factory
        self._preview_builder = preview_builder
        self._unmasker = ResponseUnmasker()

    def summarize(
        self,
        result: QueryExecutionResult,
        token_mappings: Sequence[TokenMappingEntry],
        *,
        safe_question: str | None = None,
    ) -> tuple[str, SummarySource]:
        if result.row_count == 0:
            return "No rows matched the query.", SummarySource.DETERMINISTIC

        preview = self._preview_builder.build(result, token_mappings)
        messages = [
            LLMMessage(role=LLMRole.SYSTEM, content=SQL_RESULT_SUMMARY_SYSTEM_PROMPT),
            LLMMessage(role=LLMRole.SYSTEM, content=f"PROTECTED RESULT PREVIEW:\n{preview}"),
        ]
        if safe_question and safe_question.strip():
            protected_question = self._preview_builder.protect_text(
                safe_question,
                token_mappings,
            )
            messages.append(LLMMessage(role=LLMRole.USER, content=protected_question))
        request = LLMRequest(messages=messages, temperature=0)

        try:
            client = self._llm_client_factory()
            output = client.generate_structured(request, SQLResultSummary)
            summary = self._unmasker.unmask(output.summary, token_mappings)
        except (LLMError, PrivacyUnmaskingError, ValidationError):
            return _fallback_summary(result), SummarySource.DETERMINISTIC_FALLBACK
        return summary, SummarySource.LLM


def _fallback_summary(result: QueryExecutionResult) -> str:
    summary = f"Query returned {result.row_count} rows across {len(result.columns)} columns."
    if result.truncated:
        return f"{summary[:-1]}; the returned result was truncated."
    return summary
