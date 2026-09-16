"""Small state-transforming nodes for the standard NLP-to-SQL LangGraph."""

from app.metadata.registry import MetadataRegistry
from app.nlp2sql.exceptions import NLP2SQLMetadataError
from app.nlp2sql.generator import SQLGenerator
from app.nlp2sql.models import SQLValidationDecision
from app.nlp2sql.selectors import DomainSelector, TableSelector
from app.nlp2sql.state import NLP2SQLState
from app.nlp2sql.validation.service import SQLValidationService


class NLP2SQLNodes:
    """Injected node collection with no database-row or execution dependency."""

    def __init__(
        self,
        registry: MetadataRegistry,
        domain_selector: DomainSelector,
        table_selector: TableSelector,
        sql_generator: SQLGenerator,
        sql_validator: SQLValidationService,
    ) -> None:
        self._registry = registry
        self._domain_selector = domain_selector
        self._table_selector = table_selector
        self._sql_generator = sql_generator
        self._sql_validator = sql_validator

    def refresh_metadata(self, state: NLP2SQLState) -> NLP2SQLState:
        """Verify the injected current registry and expose compact domain names."""

        domains = self._registry.list_domains()
        if not domains or not self._registry.list_tables():
            raise NLP2SQLMetadataError("NLP-to-SQL metadata is unavailable")
        return {"available_domains": tuple(domain.name for domain in domains)}

    def select_domains(self, state: NLP2SQLState) -> NLP2SQLState:
        selected = self._domain_selector.select(
            state["safe_question"],
            self._registry.list_domains(),
        )
        return {
            "selected_domains": selected,
            "llm_call_count": state.get("llm_call_count", 0) + 1,
        }

    def select_tables(self, state: NLP2SQLState) -> NLP2SQLState:
        candidate_names = sorted(
            {
                table.name
                for domain_name in state["selected_domains"]
                for table in self._registry.tables_for_domain(domain_name)
            }
        )
        candidate_tables = tuple(self._registry.get_table(name) for name in candidate_names)
        selected = self._table_selector.select(state["safe_question"], candidate_tables)
        return {
            "candidate_tables": tuple(candidate_names),
            "selected_tables": selected,
            "llm_call_count": state.get("llm_call_count", 0) + 1,
        }

    def build_metadata(self, state: NLP2SQLState) -> NLP2SQLState:
        context = self._registry.build_context(state["selected_tables"])
        if not context.strip():
            raise NLP2SQLMetadataError("Selected-table metadata context is unavailable")
        return {"metadata_context": context}

    def generate_sql(self, state: NLP2SQLState) -> NLP2SQLState:
        sql = self._sql_generator.generate(
            state["safe_question"],
            state["metadata_context"],
        )
        return {
            "initial_sql": sql,
            "generated_sql": sql,
            "previous_sql": None,
            "generation_attempt": 1,
            "rewrite_count": 0,
            "final_sql": None,
            "llm_call_count": state.get("llm_call_count", 0) + 1,
        }

    def validate_sql(self, state: NLP2SQLState) -> NLP2SQLState:
        """Apply all validation layers and expose only accepted SQL as final SQL."""

        result = self._sql_validator.validate(
            safe_question=state["safe_question"],
            selected_domains=state["selected_domains"],
            selected_tables=state["selected_tables"],
            metadata_context=state["metadata_context"],
            generated_sql=state["generated_sql"],
            generation_attempt=state["generation_attempt"],
            rewrite_count=state["rewrite_count"],
        )
        final_sql = (
            state["generated_sql"] if result.decision is SQLValidationDecision.ACCEPT else None
        )
        return {
            "validation_result": result,
            "final_sql": final_sql,
            "llm_call_count": state.get("llm_call_count", 0) + int(result.semantic_assessed),
        }

    def regenerate_sql(self, state: NLP2SQLState) -> NLP2SQLState:
        """Correct the current candidate once without repeating metadata selection."""

        validation = state["validation_result"]
        previous_sql = state["generated_sql"]
        sql = self._sql_generator.regenerate(
            safe_question=state["safe_question"],
            selected_domains=state["selected_domains"],
            selected_tables=state["selected_tables"],
            metadata_context=state["metadata_context"],
            previous_sql=previous_sql,
            validation_issues=validation.issues,
            rewrite_guidance=validation.rewrite_guidance,
        )
        return {
            "previous_sql": previous_sql,
            "generated_sql": sql,
            "generation_attempt": state["generation_attempt"] + 1,
            "rewrite_count": state["rewrite_count"] + 1,
            "final_sql": None,
            "llm_call_count": state.get("llm_call_count", 0) + 1,
        }
