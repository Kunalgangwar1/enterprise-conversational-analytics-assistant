"""PostgreSQL metadata integration tests for validated, unexecuted SQL."""

from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, event, text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import get_settings
from app.db.session import create_database_engine
from app.metadata.refresh import build_registry
from app.nlp2sql import NLP2SQLAgent
from app.nlp2sql.models import SQLValidationDecision
from tests.llm.fakes import FakeLLMClient
from tests.nlp2sql.helpers import SPECIALTY_SQL, workflow_fake

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def nlp2sql_engine() -> Iterator[Engine]:
    settings = get_settings()
    engine = create_database_engine(str(settings.database_url))
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError:
        engine.dispose()
        pytest.fail("Could not connect to the configured PostgreSQL DATABASE_URL")

    yield engine
    engine.dispose()


def test_actual_registry_traverses_all_nodes_without_querying_rows(
    nlp2sql_engine: Engine,
) -> None:
    registry = build_registry(nlp2sql_engine)
    statements_during_graph: list[str] = []

    def record_statement(
        _connection: object,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _executemany: bool,
    ) -> None:
        statements_during_graph.append(statement)

    event.listen(nlp2sql_engine, "before_cursor_execute", record_statement)
    try:
        fake = workflow_fake()
        result = NLP2SQLAgent(registry, fake).generate_sql(
            "Show total paid claims by provider specialty."
        )
    finally:
        event.remove(nlp2sql_engine, "before_cursor_execute", record_statement)

    assert len(registry.list_domains()) == 5
    assert len(registry.list_tables()) == 7
    assert result.generated_sql == SPECIALTY_SQL
    assert result.final_sql == SPECIALTY_SQL
    assert result.validation.decision is SQLValidationDecision.ACCEPT
    assert result.llm_call_count == 4
    assert statements_during_graph == []


def test_rewrite_path_uses_actual_metadata_without_executing_sql(
    nlp2sql_engine: Engine,
) -> None:
    registry = build_registry(nlp2sql_engine)
    statements_during_graph: list[str] = []

    def record_statement(
        _connection: object,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _executemany: bool,
    ) -> None:
        statements_during_graph.append(statement)

    initial_sql = (
        "SELECT c.provider_id, SUM(c.paid_amount) AS total_paid "
        "FROM claims AS c GROUP BY c.provider_id"
    )
    fake = FakeLLMClient(
        structured_payloads=[
            {"selected_domains": ["claims", "provider_network"]},
            {"selected_tables": ["claims", "providers"]},
            {"sql": initial_sql},
            {
                "score": 0.6,
                "issues": ["Provider specialty is missing."],
                "rewrite_guidance": "Join providers and group by specialty.",
            },
            {"sql": SPECIALTY_SQL},
            {"score": 0.95, "issues": [], "rewrite_guidance": None},
        ]
    )

    event.listen(nlp2sql_engine, "before_cursor_execute", record_statement)
    try:
        result = NLP2SQLAgent(registry, fake).generate_sql(
            "Show total paid claims by provider specialty."
        )
    finally:
        event.remove(nlp2sql_engine, "before_cursor_execute", record_statement)

    assert result.validation.decision is SQLValidationDecision.ACCEPT
    assert result.initial_sql == initial_sql
    assert result.final_sql == SPECIALTY_SQL
    assert result.rewrite_count == 1
    assert statements_during_graph == []
