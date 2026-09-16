"""PostgreSQL integration tests for accepted SQL execution and presentation."""

from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, create_engine
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import get_settings
from app.db.query.postgres import PostgresQueryExecutor
from app.nlp2sql.models import SQLValidationDecision
from app.privacy import IdentifierType, TokenMappingEntry
from app.sql_results import (
    ChartMetadataBuilder,
    ChartType,
    SQLExecutionService,
    SQLResultSummarizer,
    SQLTokenResolver,
)
from app.sql_results.preview import SQLSummaryPreviewBuilder
from tests.llm.fakes import FakeLLMClient

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def analytics_query_engine() -> Iterator[Engine]:
    settings = get_settings()
    if settings.query_test_database_url is None:
        pytest.skip("QUERY_TEST_DATABASE_URL is not configured; SQL result integration skipped")

    engine = create_engine(str(settings.query_test_database_url), pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            connection.exec_driver_sql("SELECT 1")
    except SQLAlchemyError:
        engine.dispose()
        pytest.fail("Could not connect to the isolated PostgreSQL QUERY_TEST_DATABASE_URL")
    yield engine
    engine.dispose()


def _service(
    engine: Engine,
    fake: FakeLLMClient,
    *,
    max_rows: int = 3,
) -> SQLExecutionService:
    return SQLExecutionService(
        PostgresQueryExecutor(engine, max_rows=max_rows, timeout_ms=5_000),
        SQLTokenResolver(),
        SQLResultSummarizer(
            lambda: fake,
            SQLSummaryPreviewBuilder(max_rows=50, max_chars=12_000),
        ),
        ChartMetadataBuilder(),
    )


def _table_exists(engine: Engine, table: str) -> bool:
    result = PostgresQueryExecutor(engine, max_rows=1, timeout_ms=5_000).execute(
        f"SELECT to_regclass('public.{table}') AS table_name"
    )
    return result.rows[0]["table_name"] is not None


def test_actual_executor_returns_bounded_summary_and_chart_without_modification(
    analytics_query_engine: Engine,
) -> None:
    if not _table_exists(analytics_query_engine, "claims"):
        pytest.skip("Phase 3 schema is not present in QUERY_TEST_DATABASE_URL")
    executor = PostgresQueryExecutor(analytics_query_engine, max_rows=1, timeout_ms=5_000)
    before = executor.execute("SELECT COUNT(*) AS claim_count FROM claims").rows[0]["claim_count"]
    fake = FakeLLMClient(
        structured_payload={"summary": "Returned claims are grouped by facility type."}
    )
    sql = (
        "SELECT f.facility_type, COUNT(c.id) AS claim_count, "
        "ROUND(AVG(c.allowed_amount), 2) AS avg_allowed_amount "
        "FROM claims AS c "
        "JOIN providers AS p ON c.provider_id = p.id "
        "JOIN facilities AS f ON p.facility_id = f.id "
        "GROUP BY f.facility_type ORDER BY claim_count DESC"
    )

    result = _service(analytics_query_engine, fake).execute(
        final_sql=sql,
        decision=SQLValidationDecision.ACCEPT,
    )
    after = executor.execute("SELECT COUNT(*) AS claim_count FROM claims").rows[0]["claim_count"]

    assert result.columns == ["facility_type", "claim_count", "avg_allowed_amount"]
    assert result.row_count <= 3
    assert result.summary
    assert result.chart.chart_type in {ChartType.BAR, ChartType.TABLE}
    assert before == after


def test_tokenized_member_filter_resolves_only_at_execution_boundary(
    analytics_query_engine: Engine,
) -> None:
    if not _table_exists(analytics_query_engine, "members"):
        pytest.skip("Phase 3 schema is not present in QUERY_TEST_DATABASE_URL")
    probe = PostgresQueryExecutor(analytics_query_engine, max_rows=1, timeout_ms=5_000).execute(
        "SELECT member_external_id FROM members WHERE member_external_id = 'M000001'"
    )
    if probe.row_count == 0:
        pytest.skip("Deterministic seeded member M000001 is not present")

    fake = FakeLLMClient(structured_payload={"summary": "Member T001 matched."})
    mapping = (
        TokenMappingEntry(
            token="T001",
            original_value="M000001",
            identifier_type=IdentifierType.MEMBER,
        ),
    )
    result = _service(analytics_query_engine, fake, max_rows=1).execute(
        final_sql=("SELECT member_external_id FROM members WHERE member_external_id = 'T001'"),
        decision=SQLValidationDecision.ACCEPT,
        token_mappings=mapping,
    )

    assert result.rows == [{"member_external_id": "M000001"}]
    assert result.summary == "Member M000001 matched."
    prompt = "\n".join(message.content for message in fake.requests[0].messages)
    assert "T001" in prompt
    assert "M000001" not in prompt
