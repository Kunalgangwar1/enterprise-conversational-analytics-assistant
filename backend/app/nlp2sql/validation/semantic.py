"""Provider-neutral structured semantic SQL assessment."""

from pydantic import ValidationError

from app.llm.base import LLMClient
from app.llm.exceptions import LLMError
from app.nlp2sql.exceptions import SQLSemanticValidationError
from app.nlp2sql.models import SQLSemanticAssessment
from app.nlp2sql.prompts import build_sql_semantic_validation_request


class SemanticSQLValidator:
    """Request a bounded semantic score after deterministic validation passes."""

    def __init__(self, llm_client: LLMClient) -> None:
        self._llm_client = llm_client

    def assess(
        self,
        *,
        safe_question: str,
        selected_domains: tuple[str, ...],
        selected_tables: tuple[str, ...],
        metadata_context: str,
        generated_sql: str,
    ) -> SQLSemanticAssessment:
        request = build_sql_semantic_validation_request(
            safe_question=safe_question,
            selected_domains=selected_domains,
            selected_tables=selected_tables,
            metadata_context=metadata_context,
            generated_sql=generated_sql,
        )
        try:
            return self._llm_client.generate_structured(request, SQLSemanticAssessment)
        except (LLMError, ValidationError) as exc:
            raise SQLSemanticValidationError(
                "Semantic SQL assessment could not be completed"
            ) from exc
