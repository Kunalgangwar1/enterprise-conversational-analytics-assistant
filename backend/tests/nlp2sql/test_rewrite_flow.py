"""End-to-end graph tests for direct outcomes and one controlled rewrite."""

import pytest

from app.metadata.registry import MetadataRegistry
from app.nlp2sql import NLP2SQLAgent
from app.nlp2sql.models import (
    DomainSelection,
    SQLGeneration,
    SQLSemanticAssessment,
    SQLValidationDecision,
    TableSelection,
)
from tests.llm.fakes import FakeLLMClient
from tests.nlp2sql.helpers import SPECIALTY_SQL, workflow_fake

INSUFFICIENT_SQL = (
    "SELECT c.provider_id, SUM(c.paid_amount) AS total_paid FROM claims AS c GROUP BY c.provider_id"
)


def test_semantic_rewrite_can_produce_accepted_final_sql(
    metadata_registry: MetadataRegistry,
) -> None:
    fake = FakeLLMClient(
        structured_payloads=[
            {"selected_domains": ["claims", "provider_network"]},
            {"selected_tables": ["claims", "providers"]},
            {"sql": INSUFFICIENT_SQL},
            {
                "score": 0.65,
                "issues": ["Query groups by provider_id rather than provider specialty."],
                "rewrite_guidance": "Join providers and group by providers.specialty.",
            },
            {"sql": SPECIALTY_SQL},
            {"score": 0.95, "issues": [], "rewrite_guidance": None},
        ]
    )

    result = NLP2SQLAgent(metadata_registry, fake).generate_sql(
        "Show total paid claims by specialty."
    )

    assert result.initial_sql == INSUFFICIENT_SQL
    assert result.generated_sql == SPECIALTY_SQL
    assert result.final_sql == SPECIALTY_SQL
    assert result.validation.decision is SQLValidationDecision.ACCEPT
    assert result.generation_attempt == 2
    assert result.rewrite_count == 1
    assert result.llm_call_count == 6
    assert fake.structured_response_models.count(SQLGeneration) == 2
    assert fake.structured_response_models.count(SQLSemanticAssessment) == 2
    rewrite_grounding = fake.requests[4].messages[1].content
    assert INSUFFICIENT_SQL in rewrite_grounding
    assert "groups by provider_id" in rewrite_grounding


def test_second_rewrite_decision_becomes_terminal_reject(
    metadata_registry: MetadataRegistry,
) -> None:
    fake = FakeLLMClient(
        structured_payloads=[
            {"selected_domains": ["claims", "provider_network"]},
            {"selected_tables": ["claims", "providers"]},
            {"sql": INSUFFICIENT_SQL},
            {"score": 0.6, "issues": ["Wrong dimension."], "rewrite_guidance": "Fix it."},
            {"sql": INSUFFICIENT_SQL},
            {"score": 0.6, "issues": ["Still wrong."], "rewrite_guidance": "Fix it."},
        ]
    )

    result = NLP2SQLAgent(metadata_registry, fake).generate_sql(
        "Show total paid claims by specialty."
    )

    assert result.validation.decision is SQLValidationDecision.REJECT
    assert result.validation.reason_code == "rewrite_budget_exhausted"
    assert result.final_sql is None
    assert result.generation_attempt == 2
    assert result.rewrite_count == 1
    assert fake.structured_response_models.count(SQLGeneration) == 2


def test_schema_hallucination_rewrites_without_first_semantic_call(
    metadata_registry: MetadataRegistry,
) -> None:
    fake = FakeLLMClient(
        structured_payloads=[
            {"selected_domains": ["claims", "provider_network"]},
            {"selected_tables": ["claims", "providers"]},
            {"sql": "SELECT c.invented_amount FROM claims AS c"},
            {"sql": SPECIALTY_SQL},
            {"score": 0.95, "issues": [], "rewrite_guidance": None},
        ]
    )

    result = NLP2SQLAgent(metadata_registry, fake).generate_sql("Show paid claims by specialty.")

    assert result.validation.decision is SQLValidationDecision.ACCEPT
    assert result.final_sql == SPECIALTY_SQL
    assert result.llm_call_count == 5
    assert fake.structured_response_models == [
        DomainSelection,
        TableSelection,
        SQLGeneration,
        SQLGeneration,
        SQLSemanticAssessment,
    ]


@pytest.mark.parametrize(
    "unsafe_sql",
    [
        "DELETE FROM claims",
        "UPDATE claims SET claim_status = 'paid'",
        "DROP TABLE claims",
        "SELECT 1; DROP TABLE claims",
        "SELECT * INTO copied_claims FROM claims",
    ],
)
def test_hard_reject_never_calls_semantic_validator_or_regenerator(
    metadata_registry: MetadataRegistry,
    unsafe_sql: str,
) -> None:
    fake = workflow_fake(domains=["claims"], tables=["claims"], sql=unsafe_sql)

    result = NLP2SQLAgent(metadata_registry, fake).generate_sql("Show paid claims.")

    assert result.validation.decision is SQLValidationDecision.REJECT
    assert result.final_sql is None
    assert result.generation_attempt == 1
    assert result.rewrite_count == 0
    assert len(fake.requests) == 3
    assert fake.structured_response_models.count(SQLGeneration) == 1
    assert SQLSemanticAssessment not in fake.structured_response_models


def test_malformed_sql_rewrites_once_then_accepts(metadata_registry: MetadataRegistry) -> None:
    fake = FakeLLMClient(
        structured_payloads=[
            {"selected_domains": ["claims", "provider_network"]},
            {"selected_tables": ["claims", "providers"]},
            {"sql": "SELECT * FROM"},
            {"sql": SPECIALTY_SQL},
            {"score": 0.95, "issues": [], "rewrite_guidance": None},
        ]
    )

    result = NLP2SQLAgent(metadata_registry, fake).generate_sql("Show paid claims by specialty.")

    assert result.validation.decision is SQLValidationDecision.ACCEPT
    assert result.rewrite_count == 1
    assert result.final_sql == SPECIALTY_SQL


def test_malformed_sql_after_rewrite_budget_is_rejected(
    metadata_registry: MetadataRegistry,
) -> None:
    fake = FakeLLMClient(
        structured_payloads=[
            {"selected_domains": ["claims"]},
            {"selected_tables": ["claims"]},
            {"sql": "SELECT * FROM"},
            {"sql": "SELECT paid_amount FROM"},
        ]
    )

    result = NLP2SQLAgent(metadata_registry, fake).generate_sql("Show paid claims.")

    assert result.validation.decision is SQLValidationDecision.REJECT
    assert result.validation.reason_code == "rewrite_budget_exhausted"
    assert result.final_sql is None
    assert result.rewrite_count == 1
    assert len(fake.requests) == 4
