"""SQL-specific bounded multi-hop agent over the standard NLP-to-SQL path."""

from collections.abc import Callable, Sequence
from time import monotonic

from langgraph.graph.state import CompiledStateGraph

from app.db.query.base import QueryExecutor
from app.db.query.exceptions import QueryError
from app.llm.base import LLMClient
from app.nlp2sql.agent import NLP2SQLAgent
from app.nlp2sql.exceptions import NLP2SQLError
from app.nlp2sql.models import SQLValidationDecision
from app.nlp2sql.multihop.budget import MultiHopBudget
from app.nlp2sql.multihop.exceptions import (
    MultiHopDisabledError,
    MultiHopExecutionError,
)
from app.nlp2sql.multihop.executor import BudgetedQueryExecutor
from app.nlp2sql.multihop.graph import build_multihop_graph
from app.nlp2sql.multihop.models import HopResult, MultiHopResult
from app.nlp2sql.multihop.planner import MultiHopPlanner, validate_multihop_plan
from app.nlp2sql.multihop.state import MultiHopState
from app.nlp2sql.multihop.synthesis import MultiHopSynthesisService, render_multihop_markdown
from app.privacy.models import TokenMappingEntry
from app.privacy.unmasker import ResponseUnmasker
from app.routing.heuristics import detect_forecasting_intent
from app.sql_results.exceptions import SQLResultsError
from app.sql_results.preview import SQLSummaryPreviewBuilder
from app.sql_results.token_resolver import SQLTokenResolver


class MultiHopNodes:
    def __init__(
        self,
        *,
        planner: MultiHopPlanner,
        nlp2sql_agent: NLP2SQLAgent,
        query_executor: BudgetedQueryExecutor,
        preview_builder: SQLSummaryPreviewBuilder,
        synthesis_service: MultiHopSynthesisService,
        max_hops: int,
        max_rows_per_hop: int,
        total_row_budget: int,
        total_timeout_seconds: float,
        query_timeout_ms: int,
        dependency_context_max_chars: int,
        clock: Callable[[], float],
    ) -> None:
        self._planner = planner
        self._nlp2sql_agent = nlp2sql_agent
        self._query_executor = query_executor
        self._preview_builder = preview_builder
        self._synthesis = synthesis_service
        self._max_hops = max_hops
        self._max_rows_per_hop = max_rows_per_hop
        self._total_row_budget = total_row_budget
        self._total_timeout_seconds = total_timeout_seconds
        self._query_timeout_ms = query_timeout_ms
        self._dependency_context_max_chars = dependency_context_max_chars
        self._clock = clock
        self._token_resolver = SQLTokenResolver()

    def plan(self, state: MultiHopState) -> MultiHopState:
        plan = self._planner.create_plan(state["safe_question"])
        ordered = validate_multihop_plan(plan, max_hops=self._max_hops)
        budget = MultiHopBudget(
            hops_planned=len(ordered),
            max_hops=self._max_hops,
            max_rows_per_hop=self._max_rows_per_hop,
            total_row_budget=self._total_row_budget,
            total_timeout_seconds=self._total_timeout_seconds,
            query_timeout_ms=self._query_timeout_ms,
            clock=self._clock,
        )
        return {
            "plan": plan,
            "ordered_hops": ordered,
            "current_hop_index": 0,
            "hop_results": (),
            "budget": budget,
        }

    def execute_hop(self, state: MultiHopState) -> MultiHopState:
        hop = state["ordered_hops"][state["current_hop_index"]]
        existing = state.get("hop_results", ())
        by_id = {result.hop_id: result for result in existing}
        dependency_context = self._dependency_context(hop.depends_on, by_id)
        analytical_question = hop.sub_question
        if dependency_context:
            analytical_question = (
                f"{analytical_question}\n\nBEGIN PROTECTED DEPENDENCY RESULTS\n"
                f"{dependency_context}\nEND PROTECTED DEPENDENCY RESULTS"
            )
        allowance = state["budget"].allowance_for_next_hop()
        try:
            generated = self._nlp2sql_agent.generate_sql(analytical_question)
            if (
                generated.validation.decision is not SQLValidationDecision.ACCEPT
                or generated.final_sql is None
            ):
                raise MultiHopExecutionError(
                    f"Required hop '{hop.hop_id}' did not produce accepted SQL"
                )
            executable_sql = self._token_resolver.resolve(
                generated.final_sql,
                state.get("token_mappings", ()),
            )
            query_result = self._query_executor.execute(executable_sql, allowance)
        except MultiHopExecutionError:
            raise
        except (NLP2SQLError, QueryError, SQLResultsError) as exc:
            raise MultiHopExecutionError(
                f"Required hop '{hop.hop_id}' could not be completed"
            ) from exc

        state["budget"].record_hop(query_result.row_count, allowance)
        preview = self._preview_builder.build(
            query_result,
            state.get("token_mappings", ()),
        )
        hop_result = HopResult(
            hop_id=hop.hop_id,
            sub_question=hop.sub_question,
            selected_domains=generated.selected_domains,
            selected_tables=generated.selected_tables,
            safe_sql=generated.final_sql,
            columns=tuple(query_result.columns),
            protected_preview=preview,
            row_count=query_result.row_count,
            truncated=query_result.truncated,
            elapsed_ms=query_result.elapsed_ms,
        )
        return {
            "hop_results": (*existing, hop_result),
            "current_hop_index": state["current_hop_index"] + 1,
        }

    def check_budget_and_remaining(self, state: MultiHopState) -> MultiHopState:
        if state["current_hop_index"] < len(state["ordered_hops"]):
            state["budget"].allowance_for_next_hop()
        return {}

    def prepare_next_hop(self, state: MultiHopState) -> MultiHopState:
        return {}

    def synthesize(self, state: MultiHopState) -> MultiHopState:
        synthesis = self._synthesis.synthesize(state["safe_question"], state["hop_results"])
        return {
            "synthesis": synthesis,
            "answer_markdown": render_multihop_markdown(synthesis),
        }

    def _dependency_context(
        self,
        dependencies: Sequence[str],
        results_by_id: dict[str, HopResult],
    ) -> str:
        parts = [
            f"Hop {dependency}: {results_by_id[dependency].protected_preview}"
            for dependency in dependencies
        ]
        return "\n".join(parts)[: self._dependency_context_max_chars]


class MultiHopNLP2SQLAgent:
    """Plan, validate, execute, and synthesize dependent read-only SQL hops."""

    def __init__(
        self,
        *,
        enabled: bool,
        llm_client: LLMClient,
        nlp2sql_agent: NLP2SQLAgent,
        query_executor: QueryExecutor,
        max_hops: int,
        max_rows_per_hop: int,
        total_row_budget: int,
        total_timeout_seconds: float,
        query_timeout_ms: int,
        preview_max_rows: int = 50,
        preview_max_chars: int = 12_000,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        self._enabled = enabled
        nodes = MultiHopNodes(
            planner=MultiHopPlanner(llm_client, max_hops=max_hops),
            nlp2sql_agent=nlp2sql_agent,
            query_executor=BudgetedQueryExecutor(query_executor),
            preview_builder=SQLSummaryPreviewBuilder(
                max_rows=min(preview_max_rows, max_rows_per_hop),
                max_chars=preview_max_chars,
            ),
            synthesis_service=MultiHopSynthesisService(llm_client),
            max_hops=max_hops,
            max_rows_per_hop=max_rows_per_hop,
            total_row_budget=total_row_budget,
            total_timeout_seconds=total_timeout_seconds,
            query_timeout_ms=query_timeout_ms,
            dependency_context_max_chars=preview_max_chars,
            clock=clock,
        )
        self._graph = build_multihop_graph(nodes)
        self._unmasker = ResponseUnmasker()

    @property
    def graph(self) -> CompiledStateGraph:
        return self._graph

    def run(
        self,
        safe_question: str,
        token_mappings: Sequence[TokenMappingEntry] = (),
    ) -> MultiHopResult:
        if not self._enabled:
            raise MultiHopDisabledError("Multi-hop NLP-to-SQL is disabled by rollout policy")
        if not safe_question.strip():
            raise MultiHopExecutionError("A privacy-safe analytical question is required")
        if detect_forecasting_intent(safe_question) is not None:
            raise MultiHopExecutionError(
                "Forecasting requests are outside multi-hop NLP-to-SQL scope"
            )
        output = self._graph.invoke(
            {"safe_question": safe_question, "token_mappings": tuple(token_mappings)}
        )
        protected_markdown = output["answer_markdown"]
        return MultiHopResult(
            answer_markdown=self._unmasker.unmask(protected_markdown, token_mappings),
            synthesis=output["synthesis"],
            hops=output["hop_results"],
            budget=output["budget"].snapshot(),
        )
