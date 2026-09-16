"""Application wrapper around the validated standard NLP-to-SQL graph."""

from langgraph.graph.state import CompiledStateGraph

from app.core.config import get_settings
from app.llm.base import LLMClient
from app.metadata.registry import MetadataRegistry
from app.nlp2sql.exceptions import NLP2SQLError
from app.nlp2sql.generator import SQLGenerator
from app.nlp2sql.graph import build_nlp2sql_graph
from app.nlp2sql.models import NLP2SQLResult
from app.nlp2sql.nodes import NLP2SQLNodes
from app.nlp2sql.selectors import DomainSelector, TableSelector
from app.nlp2sql.validation import (
    SchemaGroundingValidator,
    SemanticSQLValidator,
    SQLValidationService,
    StructuralSQLValidator,
)


class NLP2SQLAgent:
    """Generate and validate SQL from a privacy-safe question without executing it."""

    def __init__(
        self,
        registry: MetadataRegistry,
        llm_client: LLMClient,
        *,
        max_domains: int | None = None,
        max_tables: int | None = None,
    ) -> None:
        settings = get_settings()
        domain_limit = settings.nlp2sql_max_domains if max_domains is None else max_domains
        table_limit = settings.nlp2sql_max_tables if max_tables is None else max_tables
        nodes = NLP2SQLNodes(
            registry,
            DomainSelector(llm_client, max_domains=domain_limit),
            TableSelector(llm_client, max_tables=table_limit),
            SQLGenerator(llm_client),
            SQLValidationService(
                StructuralSQLValidator(),
                SchemaGroundingValidator(registry),
                SemanticSQLValidator(llm_client),
                accept_score=settings.nlp2sql_accept_score,
                rewrite_score=settings.nlp2sql_rewrite_score,
                max_rewrites=settings.nlp2sql_max_rewrites,
            ),
        )
        self._graph = build_nlp2sql_graph(nodes)

    @property
    def graph(self) -> CompiledStateGraph:
        """Expose the compiled graph for internal inspection and testing."""

        return self._graph

    def generate_sql(self, safe_question: str) -> NLP2SQLResult:
        """Run the bounded graph and return its validated, unexecuted result."""

        if not safe_question.strip():
            raise NLP2SQLError("A privacy-safe analytical question is required")
        output = self._graph.invoke({"safe_question": safe_question, "llm_call_count": 0})
        return NLP2SQLResult(
            selected_domains=output["selected_domains"],
            selected_tables=output["selected_tables"],
            initial_sql=output["initial_sql"],
            generated_sql=output["generated_sql"],
            final_sql=output.get("final_sql"),
            validation=output["validation_result"],
            generation_attempt=output["generation_attempt"],
            rewrite_count=output["rewrite_count"],
            llm_call_count=output["llm_call_count"],
        )
