"""Structured PostgreSQL generation and one feedback-guided regeneration."""

from pydantic import ValidationError

from app.llm.base import LLMClient
from app.llm.exceptions import LLMStructuredOutputError
from app.llm.models import LLMRequest
from app.nlp2sql.exceptions import SQLGenerationError
from app.nlp2sql.models import SQLGeneration
from app.nlp2sql.prompts import build_sql_generation_request, build_sql_rewrite_request


class SQLGenerator:
    """Generate one metadata-grounded PostgreSQL query through LLMClient."""

    def __init__(self, llm_client: LLMClient) -> None:
        self._llm_client = llm_client

    def generate(self, safe_question: str, metadata_context: str) -> str:
        request = build_sql_generation_request(safe_question, metadata_context)
        return self._generate_from_request(request)

    def regenerate(
        self,
        *,
        safe_question: str,
        selected_domains: tuple[str, ...],
        selected_tables: tuple[str, ...],
        metadata_context: str,
        previous_sql: str,
        validation_issues: tuple[str, ...],
        rewrite_guidance: str | None,
    ) -> str:
        """Generate one correction from deterministic or semantic validation feedback."""

        request = build_sql_rewrite_request(
            safe_question=safe_question,
            selected_domains=selected_domains,
            selected_tables=selected_tables,
            metadata_context=metadata_context,
            previous_sql=previous_sql,
            validation_issues=validation_issues,
            rewrite_guidance=rewrite_guidance,
        )
        return self._generate_from_request(request)

    def _generate_from_request(self, request: LLMRequest) -> str:
        try:
            output = self._llm_client.generate_structured(request, SQLGeneration)
        except (LLMStructuredOutputError, ValidationError) as exc:
            raise SQLGenerationError("SQL generator returned invalid structured output") from exc
        return output.sql
