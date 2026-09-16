"""Ordered SQL validation layers and deterministic decision policy."""

from app.nlp2sql.models import SQLValidationDecision, SQLValidationResult
from app.nlp2sql.validation.schema import SchemaGroundingValidator
from app.nlp2sql.validation.semantic import SemanticSQLValidator
from app.nlp2sql.validation.structural import StructuralSQLValidator


class SQLValidationService:
    """Apply safety, schema, and semantic validation in that strict order."""

    def __init__(
        self,
        structural_validator: StructuralSQLValidator,
        schema_validator: SchemaGroundingValidator,
        semantic_validator: SemanticSQLValidator,
        *,
        accept_score: float,
        rewrite_score: float,
        max_rewrites: int,
    ) -> None:
        if not 0 <= rewrite_score < accept_score <= 1:
            raise ValueError("SQL validation thresholds must satisfy 0 <= rewrite < accept <= 1")
        if max_rewrites != 1:
            raise ValueError("The SQL rewrite budget must equal 1")
        self._structural_validator = structural_validator
        self._schema_validator = schema_validator
        self._semantic_validator = semantic_validator
        self._accept_score = accept_score
        self._rewrite_score = rewrite_score
        self._max_rewrites = max_rewrites

    def validate(
        self,
        *,
        safe_question: str,
        selected_domains: tuple[str, ...],
        selected_tables: tuple[str, ...],
        metadata_context: str,
        generated_sql: str,
        generation_attempt: int,
        rewrite_count: int,
    ) -> SQLValidationResult:
        structural = self._structural_validator.validate(generated_sql)
        if not structural.passed:
            if structural.hard_reject:
                return SQLValidationResult(
                    decision=SQLValidationDecision.REJECT,
                    score=0,
                    issues=structural.issues,
                    attempt=generation_attempt,
                    reason_code=structural.reason_code,
                )
            return self._correctable_result(
                score=0,
                issues=structural.issues,
                rewrite_guidance=structural.rewrite_guidance,
                attempt=generation_attempt,
                rewrite_count=rewrite_count,
                reason_code=structural.reason_code or "malformed_sql",
            )

        schema_issues = self._schema_validator.validate(generated_sql, selected_tables)
        if schema_issues:
            return self._correctable_result(
                score=0,
                issues=schema_issues,
                rewrite_guidance=(
                    "Use only the selected physical tables and their documented columns; "
                    "qualify ambiguous columns with a valid source alias."
                ),
                attempt=generation_attempt,
                rewrite_count=rewrite_count,
                reason_code="schema_grounding_failed",
            )

        assessment = self._semantic_validator.assess(
            safe_question=safe_question,
            selected_domains=selected_domains,
            selected_tables=selected_tables,
            metadata_context=metadata_context,
            generated_sql=generated_sql,
        )
        if assessment.score >= self._accept_score:
            decision = SQLValidationDecision.ACCEPT
            reason_code = "semantic_score_accepted"
        elif assessment.score >= self._rewrite_score:
            if rewrite_count >= self._max_rewrites:
                return SQLValidationResult(
                    decision=SQLValidationDecision.REJECT,
                    score=assessment.score,
                    issues=tuple(assessment.issues),
                    rewrite_guidance=assessment.rewrite_guidance,
                    attempt=generation_attempt,
                    reason_code="rewrite_budget_exhausted",
                    semantic_assessed=True,
                )
            decision = SQLValidationDecision.REWRITE
            reason_code = "semantic_rewrite_requested"
        else:
            decision = SQLValidationDecision.REJECT
            reason_code = "semantic_score_rejected"

        return SQLValidationResult(
            decision=decision,
            score=assessment.score,
            issues=tuple(assessment.issues),
            rewrite_guidance=assessment.rewrite_guidance,
            attempt=generation_attempt,
            reason_code=reason_code,
            semantic_assessed=True,
        )

    def _correctable_result(
        self,
        *,
        score: float,
        issues: tuple[str, ...],
        rewrite_guidance: str | None,
        attempt: int,
        rewrite_count: int,
        reason_code: str,
    ) -> SQLValidationResult:
        if rewrite_count >= self._max_rewrites:
            decision = SQLValidationDecision.REJECT
            result_reason = "rewrite_budget_exhausted"
        else:
            decision = SQLValidationDecision.REWRITE
            result_reason = reason_code
        return SQLValidationResult(
            decision=decision,
            score=score,
            issues=issues,
            rewrite_guidance=rewrite_guidance,
            attempt=attempt,
            reason_code=result_reason,
        )
