"""Read-only two-hop PostgreSQL integration through the standard validated pipeline."""

from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import get_settings
from app.db.query.postgres import PostgresQueryExecutor
from app.db.session import create_database_engine
from app.metadata.refresh import build_registry
from app.nlp2sql.agent import NLP2SQLAgent
from app.nlp2sql.multihop.agent import MultiHopNLP2SQLAgent
from tests.llm.fakes import FakeLLMClient

pytestmark = pytest.mark.integration

HOP_ONE_SQL = (
    "SELECT f.facility_type, COUNT(c.id) AS claim_count FROM claims AS c "
    "JOIN providers AS p ON p.id = c.provider_id "
    "JOIN facilities AS f ON f.id = p.facility_id "
    "GROUP BY f.facility_type ORDER BY claim_count DESC LIMIT 1"
)
HOP_TWO_SQL = (
    "SELECT f.facility_type, AVG(c.paid_amount) AS average_paid FROM claims AS c "
    "JOIN providers AS p ON p.id = c.provider_id "
    "JOIN facilities AS f ON f.id = p.facility_id "
    "GROUP BY f.facility_type ORDER BY average_paid DESC"
)


@pytest.fixture(scope="module")
def multihop_engines() -> Iterator[tuple[Engine, Engine]]:
    settings = get_settings()
    if settings.query_test_database_url is None:
        pytest.skip("QUERY_TEST_DATABASE_URL is not configured for multi-hop integration")
    metadata_engine = create_database_engine(str(settings.database_url))
    query_engine = create_engine(str(settings.query_test_database_url), pool_pre_ping=True)
    try:
        with metadata_engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        with query_engine.connect() as connection:
            connection.exec_driver_sql("SELECT 1")
    except SQLAlchemyError:
        metadata_engine.dispose()
        query_engine.dispose()
        pytest.fail("Could not connect to configured PostgreSQL integration databases")
    yield metadata_engine, query_engine
    metadata_engine.dispose()
    query_engine.dispose()


def test_actual_two_hop_analysis_is_validated_bounded_and_read_only(
    multihop_engines: tuple[Engine, Engine],
) -> None:
    metadata_engine, query_engine = multihop_engines
    executor = PostgresQueryExecutor(query_engine, max_rows=500, timeout_ms=5_000)
    if executor.execute("SELECT to_regclass('public.claims') AS name").rows[0]["name"] is None:
        pytest.skip("Phase 3 schema is not present in QUERY_TEST_DATABASE_URL")
    count_before = executor.execute("SELECT COUNT(*) AS count FROM claims").rows[0]["count"]
    fake = FakeLLMClient(
        structured_payloads=[
            {
                "hops": [
                    {
                        "hop_id": "h1",
                        "sub_question": "Find claim volume by facility type",
                        "depends_on": [],
                        "purpose": "Find the highest-volume facility type",
                    },
                    {
                        "hop_id": "h2",
                        "sub_question": "Compare average paid amount by facility type",
                        "depends_on": ["h1"],
                        "purpose": "Compare the winner with other facility types",
                    },
                ]
            },
            {"selected_domains": ["claims", "provider_network"]},
            {"selected_tables": ["claims", "providers", "facilities"]},
            {"sql": HOP_ONE_SQL},
            {"score": 0.95, "issues": [], "rewrite_guidance": None},
            {"selected_domains": ["claims", "provider_network"]},
            {"selected_tables": ["claims", "providers", "facilities"]},
            {"sql": HOP_TWO_SQL},
            {"score": 0.95, "issues": [], "rewrite_guidance": None},
            {
                "summary": "Facility claim volume and average paid amounts were compared.",
                "table": {"columns": ["Metric"], "rows": [["Completed"]]},
                "deltas": [],
            },
        ]
    )
    standard_agent = NLP2SQLAgent(build_registry(metadata_engine), fake)
    multihop_agent = MultiHopNLP2SQLAgent(
        enabled=True,
        llm_client=fake,
        nlp2sql_agent=standard_agent,
        query_executor=executor,
        max_hops=3,
        max_rows_per_hop=100,
        total_row_budget=250,
        total_timeout_seconds=20,
        query_timeout_ms=5_000,
    )

    result = multihop_agent.run(
        "Find the facility type with the highest claim volume, then compare average paid amounts."
    )
    count_after = executor.execute("SELECT COUNT(*) AS count FROM claims").rows[0]["count"]

    assert result.budget.hops_executed == 2
    assert result.budget.total_rows_returned <= 250
    assert all(hop.row_count <= 100 for hop in result.hops)
    assert result.answer_markdown
    assert count_after == count_before
