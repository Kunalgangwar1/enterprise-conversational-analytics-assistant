"""Structural classification and semantic score-policy tests."""

import pytest
from pydantic import ValidationError

from app.llm.exceptions import LLMTimeoutError
from app.metadata.registry import MetadataRegistry
from app.nlp2sql.exceptions import SQLSemanticValidationError
from app.nlp2sql.models import (
    SQLSemanticAssessment,
    SQLValidationDecision,
)
from app.nlp2sql.validation import (
    SchemaGroundingValidator,
    SemanticSQLValidator,
    SQLValidationService,
    StructuralSQLValidator,
)
from tests.llm.fakes import FakeLLMClient

VALID_SQL = "SELECT c.paid_amount FROM claims AS c"


def _service(
    registry: MetadataRegistry,
    fake: FakeLLMClient,
) -> SQLValidationService:
    return SQLValidationService(
        StructuralSQLValidator(),
        SchemaGroundingValidator(registry),
        SemanticSQLValidator(fake),
        accept_score=0.8,
        rewrite_score=0.5,
        max_rewrites=1,
    )


def _validate(
    registry: MetadataRegistry,
    fake: FakeLLMClient,
    *,
    sql: str = VALID_SQL,
    rewrite_count: int = 0,
):
    return _service(registry, fake).validate(
        safe_question="Show paid claim amounts.",
        selected_domains=("claims",),
        selected_tables=("claims",),
        metadata_context=registry.build_context(["claims"]),
        generated_sql=sql,
        generation_attempt=rewrite_count + 1,
        rewrite_count=rewrite_count,
    )


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM claims",
        "WITH paid AS (SELECT * FROM claims) SELECT * FROM paid",
    ],
)
def test_normal_select_and_cte_pass_structural_validation(sql: str) -> None:
    assert StructuralSQLValidator().validate(sql).passed is True


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM claims",
        "UPDATE claims SET claim_status = 'paid'",
        "DROP TABLE claims",
        "SELECT 1; DROP TABLE claims",
        "SELECT * INTO copied_claims FROM claims",
    ],
)
def test_unsafe_sql_is_classified_as_hard_reject(sql: str) -> None:
    outcome = StructuralSQLValidator().validate(sql)

    assert outcome.passed is False
    assert outcome.hard_reject is True


@pytest.mark.parametrize(
    ("score", "expected"),
    [
        (0.95, SQLValidationDecision.ACCEPT),
        (0.80, SQLValidationDecision.ACCEPT),
        (0.65, SQLValidationDecision.REWRITE),
        (0.50, SQLValidationDecision.REWRITE),
        (0.49, SQLValidationDecision.REJECT),
    ],
)
def test_application_maps_semantic_scores_to_decisions(
    metadata_registry: MetadataRegistry,
    score: float,
    expected: SQLValidationDecision,
) -> None:
    fake = FakeLLMClient(
        structured_payload={"score": score, "issues": [], "rewrite_guidance": None}
    )

    result = _validate(metadata_registry, fake)

    assert result.decision is expected
    assert result.semantic_assessed is True
    assert len(fake.requests) == 1


@pytest.mark.parametrize("score", [-0.01, 1.01])
def test_semantic_score_outside_unit_interval_is_rejected(score: float) -> None:
    with pytest.raises(ValidationError):
        SQLSemanticAssessment(score=score)


def test_hard_failure_skips_semantic_assessment(metadata_registry: MetadataRegistry) -> None:
    fake = FakeLLMClient(structured_payload={"score": 0.99})

    result = _validate(metadata_registry, fake, sql="DELETE FROM claims")

    assert result.decision is SQLValidationDecision.REJECT
    assert result.reason_code == "read_only_policy_violation"
    assert fake.requests == []


def test_schema_failure_skips_semantic_assessment(metadata_registry: MetadataRegistry) -> None:
    fake = FakeLLMClient(structured_payload={"score": 0.99})

    result = _validate(metadata_registry, fake, sql="SELECT c.invented FROM claims AS c")

    assert result.decision is SQLValidationDecision.REWRITE
    assert result.reason_code == "schema_grounding_failed"
    assert fake.requests == []


def test_table_grain_notes_reach_semantic_assessment(
    metadata_registry: MetadataRegistry,
) -> None:
    fake = FakeLLMClient(
        structured_payload={
            "score": 0.6,
            "issues": ["Claim-level paid_amount may be duplicated by the claim_lines join."],
            "rewrite_guidance": "Aggregate claim lines before joining claim-level measures.",
        }
    )
    context = metadata_registry.build_context(["claims", "claim_lines"])

    assessment = SemanticSQLValidator(fake).assess(
        safe_question="Show claim payments by service code.",
        selected_domains=("claims",),
        selected_tables=("claims", "claim_lines"),
        metadata_context=context,
        generated_sql=(
            "SELECT cl.service_code, SUM(c.paid_amount) FROM claims AS c "
            "JOIN claim_lines AS cl ON cl.claim_id = c.id GROUP BY cl.service_code"
        ),
    )

    assert assessment.score == 0.6
    grounding = fake.requests[0].messages[1].content
    assert "aggregating claim-level amounts after the join can duplicate" in grounding


def test_semantic_provider_failure_never_fabricates_acceptance(
    metadata_registry: MetadataRegistry,
) -> None:
    fake = FakeLLMClient(structured_payload={"score": 0.99})

    def fail(*_args: object, **_kwargs: object) -> object:
        raise LLMTimeoutError("provider timeout")

    fake.generate_structured = fail  # type: ignore[method-assign]

    with pytest.raises(SQLSemanticValidationError, match="could not be completed"):
        _validate(metadata_registry, fake)
