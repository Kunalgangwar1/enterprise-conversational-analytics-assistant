"""Tests for validation models, settings, graph topology, and call sequence."""

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.metadata.registry import MetadataRegistry
from app.nlp2sql import NLP2SQL_NODE_SEQUENCE, NLP2SQLAgent
from app.nlp2sql.models import (
    DomainSelection,
    SQLGeneration,
    SQLSemanticAssessment,
    SQLValidationDecision,
    TableSelection,
)
from tests.nlp2sql.helpers import SPECIALTY_SQL, workflow_fake


def test_nlp2sql_limits_default_and_reject_values_below_one() -> None:
    settings = Settings(_env_file=None)

    assert settings.nlp2sql_max_domains == 3
    assert settings.nlp2sql_max_tables == 5
    assert settings.nlp2sql_accept_score == 0.80
    assert settings.nlp2sql_rewrite_score == 0.50
    assert settings.nlp2sql_max_rewrites == 1
    with pytest.raises(ValidationError):
        Settings(_env_file=None, nlp2sql_max_domains=0)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, nlp2sql_max_tables=0)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, nlp2sql_rewrite_score=0.8, nlp2sql_accept_score=0.8)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, nlp2sql_rewrite_score=0.9, nlp2sql_accept_score=0.8)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, nlp2sql_max_rewrites=2)


def test_graph_has_validation_and_one_explicit_rewrite_cycle(
    metadata_registry: MetadataRegistry,
) -> None:
    agent = NLP2SQLAgent(metadata_registry, workflow_fake())
    graph = agent.graph.get_graph()
    application_nodes = tuple(name for name in graph.nodes if not name.startswith("__"))
    edges = {(edge.source, edge.target) for edge in graph.edges}

    assert NLP2SQL_NODE_SEQUENCE == (
        "refresh_metadata",
        "select_domains",
        "select_tables",
        "build_metadata",
        "generate_sql",
        "validate_sql",
        "regenerate_sql",
    )
    assert application_nodes == NLP2SQL_NODE_SEQUENCE
    assert edges == {
        ("__start__", "refresh_metadata"),
        ("refresh_metadata", "select_domains"),
        ("select_domains", "select_tables"),
        ("select_tables", "build_metadata"),
        ("build_metadata", "generate_sql"),
        ("generate_sql", "validate_sql"),
        ("validate_sql", "__end__"),
        ("validate_sql", "regenerate_sql"),
        ("regenerate_sql", "validate_sql"),
    }
    conditional_edges = {(edge.source, edge.target) for edge in graph.edges if edge.conditional}
    assert conditional_edges == {
        ("validate_sql", "__end__"),
        ("validate_sql", "regenerate_sql"),
    }
    assert all("execute" not in name for name in graph.nodes)


def test_direct_accept_is_deterministic_and_stops_after_semantic_assessment(
    metadata_registry: MetadataRegistry,
) -> None:
    fake = workflow_fake()

    result = NLP2SQLAgent(metadata_registry, fake).generate_sql(
        "Show total paid claims by specialty."
    )

    assert result.selected_domains == ("claims", "provider_network")
    assert result.selected_tables == ("claims", "providers")
    assert result.initial_sql == SPECIALTY_SQL
    assert result.generated_sql == SPECIALTY_SQL
    assert result.final_sql == SPECIALTY_SQL
    assert result.validation.decision is SQLValidationDecision.ACCEPT
    assert result.generation_attempt == 1
    assert result.rewrite_count == 0
    assert result.llm_call_count == 4
    assert fake.structured_response_models == [
        DomainSelection,
        TableSelection,
        SQLGeneration,
        SQLSemanticAssessment,
    ]


def test_graph_requires_neither_query_executor_nor_database_connection_at_invocation(
    metadata_registry: MetadataRegistry,
) -> None:
    agent = NLP2SQLAgent(metadata_registry, workflow_fake())

    result = agent.generate_sql("Show total paid claims by specialty.")

    assert result.generated_sql == SPECIALTY_SQL
