"""Deterministic multi-hop SQL test doubles."""

from app.db.query.models import QueryExecutionResult
from app.nlp2sql.models import NLP2SQLResult, SQLValidationDecision, SQLValidationResult


def nlp2sql_result(
    sql: str,
    *,
    decision: SQLValidationDecision = SQLValidationDecision.ACCEPT,
) -> NLP2SQLResult:
    return NLP2SQLResult(
        selected_domains=("claims", "provider_network"),
        selected_tables=("claims", "providers", "facilities"),
        initial_sql=sql,
        generated_sql=sql,
        final_sql=sql if decision is SQLValidationDecision.ACCEPT else None,
        validation=SQLValidationResult(
            decision=decision,
            score=1 if decision is SQLValidationDecision.ACCEPT else 0,
            attempt=1,
        ),
        generation_attempt=1,
        rewrite_count=0,
        llm_call_count=4,
    )


class RecordingNLP2SQLAgent:
    def __init__(self, results: list[NLP2SQLResult]) -> None:
        self._results = results
        self.questions: list[str] = []

    def generate_sql(self, safe_question: str) -> NLP2SQLResult:
        self.questions.append(safe_question)
        return self._results[len(self.questions) - 1]


class RecordingBoundedExecutor:
    def __init__(self, results: list[QueryExecutionResult]) -> None:
        self._results = results
        self.calls: list[tuple[str, int | None, int | None]] = []

    def execute(
        self,
        sql: str,
        *,
        max_rows: int | None = None,
        timeout_ms: int | None = None,
    ) -> QueryExecutionResult:
        self.calls.append((sql, max_rows, timeout_ms))
        return self._results[len(self.calls) - 1]
