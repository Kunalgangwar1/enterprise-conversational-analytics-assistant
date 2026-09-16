"""Mutable LangGraph state for standard NLP-to-SQL validation and rewrite."""

from typing import TypedDict

from app.nlp2sql.models import SQLValidationResult


class NLP2SQLState(TypedDict, total=False):
    """Privacy-safe schema-resolution, generation, and validation state."""

    safe_question: str
    available_domains: tuple[str, ...]
    selected_domains: tuple[str, ...]
    candidate_tables: tuple[str, ...]
    selected_tables: tuple[str, ...]
    metadata_context: str
    initial_sql: str
    generated_sql: str
    previous_sql: str | None
    validation_result: SQLValidationResult
    final_sql: str | None
    generation_attempt: int
    rewrite_count: int
    llm_call_count: int
