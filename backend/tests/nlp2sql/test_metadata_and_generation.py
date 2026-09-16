"""Tests for selected metadata context and grounded SQL generation."""

import pytest

from app.llm.models import LLMRole
from app.metadata.registry import MetadataRegistry
from app.nlp2sql import NLP2SQLAgent
from app.nlp2sql.exceptions import SQLGenerationError
from app.nlp2sql.generator import SQLGenerator
from tests.llm.fakes import FakeLLMClient
from tests.nlp2sql.helpers import FACILITY_SQL, SPECIALTY_SQL, workflow_fake


def test_generation_result_and_prompt_use_only_selected_table_context(
    metadata_registry: MetadataRegistry,
) -> None:
    fake = workflow_fake()

    result = NLP2SQLAgent(metadata_registry, fake).generate_sql(
        "Show total paid claims by specialty."
    )
    request = fake.requests[2]
    grounding = request.messages[1].content

    assert result.generated_sql == SPECIALTY_SQL
    assert result.selected_domains == ("claims", "provider_network")
    assert result.selected_tables == ("claims", "providers")
    assert request.messages[0].role is LLMRole.SYSTEM
    assert "PostgreSQL" in request.messages[0].content
    assert "Use only supplied tables and columns" in request.messages[0].content
    assert "TABLE claims" in grounding
    assert "TABLE providers" in grounding
    assert "TABLE members" not in grounding
    assert "TABLE facilities" not in grounding
    assert "claims.provider_id -> providers.id" in grounding
    assert "Grain: One row per synthetic healthcare claim." in grounding


def test_claim_line_context_preserves_grain_duplication_warning(
    metadata_registry: MetadataRegistry,
) -> None:
    context = metadata_registry.build_context(["claims", "claim_lines"])

    assert "TABLE claims" in context
    assert "TABLE claim_lines" in context
    assert "Grain: One row per service line within a synthetic healthcare claim." in context
    assert "aggregating claim-level amounts after the join can duplicate" in context


def test_facility_query_returns_deterministic_unexecuted_sql(
    metadata_registry: MetadataRegistry,
) -> None:
    fake = workflow_fake(
        tables=["claims", "providers", "facilities"],
        sql=FACILITY_SQL,
    )

    result = NLP2SQLAgent(metadata_registry, fake).generate_sql(
        "Show paid claims by facility type."
    )

    assert result.selected_tables == ("claims", "providers", "facilities")
    assert result.generated_sql == FACILITY_SQL


def test_blank_generated_sql_is_rejected() -> None:
    fake = FakeLLMClient(structured_payload={"sql": "   "})

    with pytest.raises(SQLGenerationError, match="invalid structured output"):
        SQLGenerator(fake).generate("Safe question", "TABLE claims")
