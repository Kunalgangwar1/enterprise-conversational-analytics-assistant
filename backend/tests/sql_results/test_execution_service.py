"""Accepted-SQL execution contract and bounded result propagation tests."""

import logging
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from sqlalchemy import Engine

from app.db.query.exceptions import QueryValidationError
from app.db.query.models import QueryExecutionResult
from app.db.query.postgres import PostgresQueryExecutor
from app.nlp2sql.models import SQLValidationDecision
from app.privacy import IdentifierType, TokenMappingEntry
from app.sql_results import SQLNotValidatedError, SQLTokenResolver
from app.sql_results.chart import ChartMetadataBuilder
from app.sql_results.preview import SQLSummaryPreviewBuilder
from app.sql_results.service import SQLExecutionService
from app.sql_results.summarizer import SQLResultSummarizer
from tests.llm.fakes import FakeLLMClient
from tests.sql_results.helpers import RecordingQueryExecutor, execution_service


def _result(*, truncated: bool = False) -> QueryExecutionResult:
    return QueryExecutionResult(
        columns=["specialty", "total_paid"],
        rows=[{"specialty": "Cardiology", "total_paid": Decimal("123.45")}],
        row_count=1,
        truncated=truncated,
        elapsed_ms=4.5,
    )


def test_accepted_final_sql_executes_exactly_once_and_propagates_result() -> None:
    executor = RecordingQueryExecutor(_result(truncated=True))
    fake = FakeLLMClient(structured_payload={"summary": "Cardiology totals 123.45."})
    service = execution_service(executor, lambda: fake)

    result = service.execute(
        final_sql="SELECT specialty, total_paid FROM claims",
        decision=SQLValidationDecision.ACCEPT,
    )

    assert executor.calls == ["SELECT specialty, total_paid FROM claims"]
    assert result.columns == ["specialty", "total_paid"]
    assert result.rows == _result().rows
    assert result.row_count == 1
    assert result.truncated is True
    assert result.execution_elapsed_ms == 4.5


@pytest.mark.parametrize(
    ("final_sql", "decision"),
    [
        (None, SQLValidationDecision.ACCEPT),
        ("SELECT 1", SQLValidationDecision.REJECT),
        ("SELECT 1", SQLValidationDecision.REWRITE),
    ],
)
def test_unaccepted_sql_is_rejected_before_query_executor(
    final_sql: str | None,
    decision: SQLValidationDecision,
) -> None:
    executor = RecordingQueryExecutor(_result())
    service = execution_service(
        executor,
        lambda: FakeLLMClient(structured_payload={"summary": "unused"}),
    )

    with pytest.raises(SQLNotValidatedError):
        service.execute(final_sql=final_sql, decision=decision)

    assert executor.calls == []


def test_phase_four_guard_still_rejects_manually_accepted_delete() -> None:
    engine = MagicMock(spec=Engine)
    executor = PostgresQueryExecutor(engine, max_rows=10, timeout_ms=100)
    service = SQLExecutionService(
        executor,
        SQLTokenResolver(),
        SQLResultSummarizer(
            lambda: FakeLLMClient(structured_payload={"summary": "unused"}),
            SQLSummaryPreviewBuilder(max_rows=5, max_chars=1_000),
        ),
        ChartMetadataBuilder(),
    )

    with pytest.raises(QueryValidationError):
        service.execute(
            final_sql="DELETE FROM claims",
            decision=SQLValidationDecision.ACCEPT,
        )

    engine.connect.assert_not_called()


def test_token_is_resolved_for_executor_but_never_logged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    executor = RecordingQueryExecutor(
        QueryExecutionResult(columns=[], rows=[], row_count=0, truncated=False, elapsed_ms=1)
    )
    service = execution_service(
        executor,
        lambda: FakeLLMClient(structured_payload={"summary": "unused"}),
    )
    mapping = (
        TokenMappingEntry(
            token="T001",
            original_value="M000245",
            identifier_type=IdentifierType.MEMBER,
        ),
    )

    with caplog.at_level(logging.INFO):
        result = service.execute(
            final_sql="SELECT * FROM members WHERE member_external_id = 'T001'",
            decision=SQLValidationDecision.ACCEPT,
            token_mappings=mapping,
        )

    assert executor.calls[0].endswith("member_external_id = 'M000245'")
    assert result.summary == "No rows matched the query."
    assert "M000245" not in caplog.text
    assert "T001" not in caplog.text
    assert "SELECT" not in caplog.text


def test_result_model_serializes_common_database_values_without_decimal_loss() -> None:
    executor = RecordingQueryExecutor(
        QueryExecutionResult(
            columns=["amount", "service_date", "value", "flag", "missing"],
            rows=[
                {
                    "amount": Decimal("123.4500"),
                    "service_date": date(2026, 1, 2),
                    "value": 3.5,
                    "flag": True,
                    "missing": None,
                }
            ],
            row_count=1,
            truncated=False,
            elapsed_ms=1,
        )
    )
    fake = FakeLLMClient(structured_payload={"summary": "One row returned."})

    result = execution_service(executor, lambda: fake).execute(
        final_sql="SELECT 1",
        decision=SQLValidationDecision.ACCEPT,
    )
    serialized = result.model_dump(mode="json")

    assert serialized["rows"][0]["amount"] == "123.4500"
    assert serialized["rows"][0]["service_date"] == "2026-01-02"
    assert result.rows[0]["amount"] == Decimal("123.4500")
