"""Bounded summary preview, privacy, unmasking, and fallback tests."""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from app.db.query.models import QueryExecutionResult
from app.llm.exceptions import LLMProviderError, LLMTimeoutError
from app.privacy import IdentifierType, TokenMappingEntry
from app.sql_results import SQLResultSummarizer, SummarySource
from app.sql_results.preview import SQLSummaryPreviewBuilder
from tests.llm.fakes import FakeLLMClient


def _mapping() -> tuple[TokenMappingEntry, ...]:
    return (
        TokenMappingEntry(
            token="T001",
            original_value="M000245",
            identifier_type=IdentifierType.MEMBER,
        ),
    )


def _result(*, truncated: bool = False) -> QueryExecutionResult:
    return QueryExecutionResult(
        columns=["member_external_id", "email", "phone", "claim_count"],
        rows=[
            {
                "member_external_id": "M000245",
                "email": "alice@example.com",
                "phone": "(555) 123-4567",
                "claim_count": 7,
            }
        ],
        row_count=1,
        truncated=truncated,
        elapsed_ms=2,
    )


def test_empty_result_uses_deterministic_summary_without_llm_call() -> None:
    fake = FakeLLMClient(structured_payload={"summary": "unused"})
    summarizer = SQLResultSummarizer(
        lambda: fake,
        SQLSummaryPreviewBuilder(max_rows=5, max_chars=1_000),
    )
    result = QueryExecutionResult(
        columns=["value"],
        rows=[],
        row_count=0,
        truncated=False,
        elapsed_ms=1,
    )

    summary, source = summarizer.summarize(result, ())

    assert summary == "No rows matched the query."
    assert source is SummarySource.DETERMINISTIC
    assert fake.requests == []


def test_llm_receives_protected_preview_and_current_token_is_unmasked_afterward() -> None:
    fake = FakeLLMClient(structured_payload={"summary": "Member T001 has 7 matching claims."})
    summarizer = SQLResultSummarizer(
        lambda: fake,
        SQLSummaryPreviewBuilder(max_rows=5, max_chars=2_000),
    )

    summary, source = summarizer.summarize(_result(), _mapping())

    assert summary == "Member M000245 has 7 matching claims."
    assert source is SummarySource.LLM
    prompt_text = "\n".join(message.content for message in fake.requests[0].messages)
    assert "T001" in prompt_text
    assert "[EMAIL]" in prompt_text
    assert "[PHONE]" in prompt_text
    assert "M000245" not in prompt_text
    assert "alice@example.com" not in prompt_text
    assert "(555) 123-4567" not in prompt_text


def test_only_current_known_token_is_unmasked_and_redactions_remain() -> None:
    fake = FakeLLMClient(
        structured_payload={"summary": "T001 matched T002; contact remains [EMAIL] and [PHONE]."}
    )
    summarizer = SQLResultSummarizer(
        lambda: fake,
        SQLSummaryPreviewBuilder(max_rows=5, max_chars=2_000),
    )

    summary, _ = summarizer.summarize(_result(), _mapping())

    assert "M000245 matched T002" in summary
    assert "[EMAIL]" in summary
    assert "[PHONE]" in summary


def test_preview_obeys_row_and_character_budgets_and_preserves_types() -> None:
    result = QueryExecutionResult(
        columns=["label", "amount", "day", "at"],
        rows=[
            {
                "label": f"row-{index}",
                "amount": Decimal(f"{index}.1200"),
                "day": date(2026, 1, index),
                "at": datetime(2026, 1, index, 12, tzinfo=UTC),
            }
            for index in range(1, 4)
        ],
        row_count=3,
        truncated=False,
        elapsed_ms=1,
    )
    builder = SQLSummaryPreviewBuilder(max_rows=2, max_chars=10_000)

    preview = builder.build(result, ())

    assert "row-1" in preview
    assert "row-2" in preview
    assert "row-3" not in preview
    assert '"1.1200"' in preview
    assert "2026-01-01" in preview
    assert len(SQLSummaryPreviewBuilder(max_rows=3, max_chars=80).build(result, ())) <= 80


def test_truncated_flag_is_supplied_to_summary_model() -> None:
    fake = FakeLLMClient(structured_payload={"summary": "The returned result is truncated."})
    summarizer = SQLResultSummarizer(
        lambda: fake,
        SQLSummaryPreviewBuilder(max_rows=5, max_chars=2_000),
    )

    summarizer.summarize(_result(truncated=True), _mapping())

    assert '"truncated":true' in fake.requests[0].messages[1].content


@pytest.mark.parametrize("error", [LLMTimeoutError("timeout"), LLMProviderError("provider")])
def test_llm_failure_returns_truncation_aware_deterministic_fallback(error: Exception) -> None:
    def fail():
        raise error

    summarizer = SQLResultSummarizer(
        fail,
        SQLSummaryPreviewBuilder(max_rows=5, max_chars=2_000),
    )

    summary, source = summarizer.summarize(_result(truncated=True), _mapping())

    assert summary == "Query returned 1 rows across 4 columns; the returned result was truncated."
    assert source is SummarySource.DETERMINISTIC_FALLBACK
