"""Structured domain and candidate-table selection services."""

from collections.abc import Iterable

from pydantic import ValidationError

from app.llm.base import LLMClient
from app.llm.exceptions import LLMStructuredOutputError
from app.metadata.models import DomainMetadata, TableMetadata
from app.nlp2sql.exceptions import DomainSelectionError, TableSelectionError
from app.nlp2sql.models import DomainSelection, TableSelection
from app.nlp2sql.prompts import build_domain_selection_request, build_table_selection_request


class DomainSelector:
    """Select and validate a minimal set of registered business domains."""

    def __init__(self, llm_client: LLMClient, *, max_domains: int) -> None:
        if max_domains < 1:
            raise ValueError("max_domains must be at least 1")
        self._llm_client = llm_client
        self._max_domains = max_domains

    def select(
        self,
        safe_question: str,
        available_domains: Iterable[DomainMetadata],
    ) -> tuple[str, ...]:
        domains = tuple(available_domains)
        request = build_domain_selection_request(safe_question, domains)
        try:
            output = self._llm_client.generate_structured(request, DomainSelection)
        except (LLMStructuredOutputError, ValidationError) as exc:
            raise DomainSelectionError(
                "Domain selector returned invalid structured output"
            ) from exc

        selected = _deduplicate(output.selected_domains)
        if not selected:
            raise DomainSelectionError("Domain selection cannot be empty")
        if len(selected) > self._max_domains:
            raise DomainSelectionError("Domain selection exceeds the configured maximum")
        available_names = {domain.name for domain in domains}
        if not set(selected).issubset(available_names):
            raise DomainSelectionError("Domain selection contains an unavailable domain")
        return selected


class TableSelector:
    """Select and validate tables from a domain-derived candidate set."""

    def __init__(self, llm_client: LLMClient, *, max_tables: int) -> None:
        if max_tables < 1:
            raise ValueError("max_tables must be at least 1")
        self._llm_client = llm_client
        self._max_tables = max_tables

    def select(
        self,
        safe_question: str,
        candidate_tables: Iterable[TableMetadata],
    ) -> tuple[str, ...]:
        tables = tuple(candidate_tables)
        request = build_table_selection_request(safe_question, tables)
        try:
            output = self._llm_client.generate_structured(request, TableSelection)
        except (LLMStructuredOutputError, ValidationError) as exc:
            raise TableSelectionError("Table selector returned invalid structured output") from exc

        selected = _deduplicate(output.selected_tables)
        if not selected:
            raise TableSelectionError("Table selection cannot be empty")
        if len(selected) > self._max_tables:
            raise TableSelectionError("Table selection exceeds the configured maximum")
        candidate_names = {table.name for table in tables}
        if not set(selected).issubset(candidate_names):
            raise TableSelectionError("Table selection contains a non-candidate table")
        return selected


def _deduplicate(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))
