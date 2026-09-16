"""Classification adapter around the shared Phase 4 read-only SQL guard."""

from dataclasses import dataclass

from app.db.query.exceptions import QueryValidationError, QueryValidationReason
from app.db.query.guard import validate_read_only_sql


@dataclass(frozen=True)
class StructuralValidationOutcome:
    """Deterministic safety result without using exceptions as graph control flow."""

    passed: bool
    hard_reject: bool = False
    issues: tuple[str, ...] = ()
    rewrite_guidance: str | None = None
    reason_code: str | None = None


class StructuralSQLValidator:
    """Reuse the execution-boundary guard and classify its typed failure reason."""

    _RECOVERABLE_REASONS = {
        QueryValidationReason.BLANK,
        QueryValidationReason.PARSE_ERROR,
    }

    def validate(self, sql: str) -> StructuralValidationOutcome:
        try:
            validate_read_only_sql(sql)
        except QueryValidationError as exc:
            if exc.reason in self._RECOVERABLE_REASONS:
                return StructuralValidationOutcome(
                    passed=False,
                    issues=("Generated SQL could not be parsed as one PostgreSQL query.",),
                    rewrite_guidance=(
                        "Return one syntactically valid PostgreSQL SELECT or CTE query."
                    ),
                    reason_code="malformed_sql",
                )
            return StructuralValidationOutcome(
                passed=False,
                hard_reject=True,
                issues=(self._hard_reject_issue(exc.reason),),
                reason_code="read_only_policy_violation",
            )
        return StructuralValidationOutcome(passed=True)

    @staticmethod
    def _hard_reject_issue(reason: QueryValidationReason | None) -> str:
        messages = {
            QueryValidationReason.MULTIPLE_STATEMENTS: (
                "Generated SQL contains more than one statement."
            ),
            QueryValidationReason.NON_QUERY: "Generated SQL is not a read-only query.",
            QueryValidationReason.FORBIDDEN_OPERATION: (
                "Generated SQL contains a prohibited operation."
            ),
        }
        return messages.get(reason, "Generated SQL failed the read-only safety policy.")
