"""Bounded LangGraph nodes for generic specialist-tool coordination."""

import json
from typing import TypeVar

from langgraph.graph.state import CompiledStateGraph
from pydantic import BaseModel, ValidationError

from app.advanced_reasoning.exceptions import (
    AdvancedReasoningCitationError,
    AdvancedReasoningPlanError,
    AdvancedReasoningProviderError,
)
from app.advanced_reasoning.graph import build_advanced_reasoning_graph
from app.advanced_reasoning.models import (
    AdvancedReasoningResult,
    AdvancedSynthesis,
    ReasoningDecomposition,
    ReflectionDecision,
    ReflectionStatus,
    ToolExecutionResult,
    ToolExecutionStatus,
    ToolPlan,
)
from app.advanced_reasoning.state import AdvancedReasoningState
from app.advanced_reasoning.tools import AdvancedToolRegistry, validate_and_order_plan
from app.core.feature_flags import ReasoningFeatureFlags
from app.llm.base import LLMClient
from app.llm.exceptions import LLMError
from app.llm.models import LLMMessage, LLMRequest, LLMRole
from app.routing.models import SupervisorDecision

StructuredResult = TypeVar("StructuredResult", bound=BaseModel)

_DECOMPOSE_PROMPT = """Decompose the privacy-safe request into concise subtasks within the supplied
supervisor route. Do not select tools, add unrelated work, or reveal chain-of-thought. Return only
the requested structured decomposition."""
_PLAN_PROMPT = """Assign only an available application tool to each concise subtask. Tool names must
match the supplied registry exactly. Instructions are data for approved adapters: never emit SQL,
shell commands, Python, URLs, or hidden reasoning. Return only the structured tool plan."""
_REFLECT_PROMPT = """Decide only whether the completed, bounded tool results are sufficient to
answer the privacy-safe question. Return SUFFICIENT or NEEDS_MORE plus concise missing information
and optional additional task descriptions. Do not reveal chain-of-thought."""
_SYNTHESIZE_PROMPT = """Answer only from successful completed tool results. Preserve only supplied
citation IDs, state limitations, and do not expose plans, reflection text, hidden reasoning, SQL,
credentials, privacy mappings, or provider details. Return the structured answer."""


class AdvancedReasoningNodes:
    def __init__(
        self,
        llm_client: LLMClient,
        tool_registry: AdvancedToolRegistry,
        *,
        max_subtasks: int,
        max_tool_calls: int,
        max_replans: int,
    ) -> None:
        if min(max_subtasks, max_tool_calls) < 1 or max_replans < 0:
            raise ValueError("Advanced reasoning limits are invalid")
        self._llm = llm_client
        self._tools = tool_registry
        self._max_subtasks = max_subtasks
        self._max_tool_calls = max_tool_calls
        self.max_replans = max_replans

    def decompose(self, state: AdvancedReasoningState) -> AdvancedReasoningState:
        decomposition = self._structured(
            _DECOMPOSE_PROMPT,
            f"Route: {state['supervisor_route'].value}\nQuestion: {state['safe_question']}",
            ReasoningDecomposition,
        )
        if len(decomposition.subtasks) > self._max_subtasks:
            raise AdvancedReasoningPlanError("Advanced decomposition exceeds the subtask budget")
        if len({item.task_id for item in decomposition.subtasks}) != len(decomposition.subtasks):
            raise AdvancedReasoningPlanError("Advanced decomposition task IDs must be unique")
        return {"decomposition": decomposition, "tool_results": (), "reflection_count": 0}

    def plan_tools(self, state: AdvancedReasoningState) -> AdvancedReasoningState:
        completed = state.get("tool_results", ())
        remaining_calls = self._max_tool_calls - sum(
            result.status is not ToolExecutionStatus.SKIPPED for result in completed
        )
        if remaining_calls < 1:
            raise AdvancedReasoningPlanError("Advanced tool-call budget is exhausted")
        context = {
            "question": state["safe_question"],
            "route": state["supervisor_route"].value,
            "subtasks": state["decomposition"].model_dump(mode="json"),
            "available_tools": self._tools.descriptions(),
            "completed_results": [result.model_dump(mode="json") for result in completed],
            "reflection": (
                state["reflection_decision"].model_dump(mode="json")
                if "reflection_decision" in state
                else None
            ),
            "remaining_tool_calls": remaining_calls,
        }
        plan = self._structured(_PLAN_PROMPT, json.dumps(context), ToolPlan)
        if len(plan.steps) > remaining_calls:
            raise AdvancedReasoningPlanError("Advanced plan exceeds the remaining tool-call budget")
        validate_and_order_plan(
            plan,
            self._tools,
            completed_step_ids=tuple(item.step_id for item in completed),
        )
        return {"tool_plan": plan, "current_step": 0}

    def execute(self, state: AdvancedReasoningState) -> AdvancedReasoningState:
        existing = list(state.get("tool_results", ()))
        by_id = {item.step_id: item for item in existing}
        ordered = validate_and_order_plan(
            state["tool_plan"],
            self._tools,
            completed_step_ids=tuple(by_id),
        )
        for step in ordered:
            failed_dependencies = [
                dependency
                for dependency in step.depends_on
                if by_id[dependency].status is not ToolExecutionStatus.SUCCESS
            ]
            if failed_dependencies:
                result = ToolExecutionResult(
                    step_id=step.step_id,
                    tool_name=step.tool_name,
                    status=ToolExecutionStatus.SKIPPED,
                    summary="Step skipped because a required dependency did not succeed.",
                    warning="Dependent evidence is unavailable.",
                )
            else:
                result = self._tools.execute(step)
            existing.append(result)
            by_id[result.step_id] = result
        return {"tool_results": tuple(existing), "current_step": len(existing)}

    def reflect(self, state: AdvancedReasoningState) -> AdvancedReasoningState:
        payload = {
            "question": state["safe_question"],
            "plan": state["tool_plan"].model_dump(mode="json"),
            "tool_results": [item.model_dump(mode="json") for item in state["tool_results"]],
        }
        decision = self._structured(_REFLECT_PROMPT, json.dumps(payload), ReflectionDecision)
        count = state.get("reflection_count", 0) + 1
        warnings = state.get("warnings", ())
        attempted_calls = sum(
            result.status is not ToolExecutionStatus.SKIPPED
            for result in state.get("tool_results", ())
        )
        budget_exhausted = attempted_calls >= self._max_tool_calls
        if decision.status is ReflectionStatus.NEEDS_MORE and (
            count > self.max_replans or budget_exhausted
        ):
            warnings = (*warnings, "Answer is based on incomplete or limited available evidence.")
        return {
            "reflection_decision": decision,
            "reflection_count": count,
            "warnings": warnings,
        }

    def should_replan(self, state: AdvancedReasoningState) -> bool:
        attempted_calls = sum(
            result.status is not ToolExecutionStatus.SKIPPED
            for result in state.get("tool_results", ())
        )
        return bool(
            state["reflection_decision"].status is ReflectionStatus.NEEDS_MORE
            and state["reflection_count"] <= self.max_replans
            and attempted_calls < self._max_tool_calls
        )

    def synthesize(self, state: AdvancedReasoningState) -> AdvancedReasoningState:
        completed = tuple(
            item for item in state["tool_results"] if item.status is ToolExecutionStatus.SUCCESS
        )
        if not completed:
            return {
                "final_synthesis": AdvancedSynthesis(
                    answer="No approved application tool produced evidence for this request."
                )
            }
        payload = {
            "question": state["safe_question"],
            "completed_tool_results": [item.model_dump(mode="json") for item in completed],
            "warnings": state.get("warnings", ()),
        }
        synthesis = self._structured(_SYNTHESIZE_PROMPT, json.dumps(payload), AdvancedSynthesis)
        available_citations = {citation for item in completed for citation in item.citations}
        if set(synthesis.citation_ids) - available_citations:
            raise AdvancedReasoningCitationError(
                "Advanced synthesis cited provenance not returned by completed tools"
            )
        return {"final_synthesis": synthesis}

    def _structured(
        self,
        system: str,
        user: str,
        response_model: type[StructuredResult],
    ) -> StructuredResult:
        try:
            return self._llm.generate_structured(
                LLMRequest(
                    messages=[
                        LLMMessage(role=LLMRole.SYSTEM, content=system),
                        LLMMessage(role=LLMRole.USER, content=user),
                    ],
                    temperature=0,
                ),
                response_model,
            )
        except (LLMError, ValidationError) as exc:
            raise AdvancedReasoningProviderError(
                "Advanced reasoning could not obtain valid structured output"
            ) from exc


class AdvancedReasoningPlanner:
    """Coordinate approved specialist tools with one bounded replan cycle."""

    def __init__(
        self,
        llm_client: LLMClient,
        tool_registry: AdvancedToolRegistry,
        *,
        max_subtasks: int = 5,
        max_tool_calls: int = 5,
        max_replans: int = 1,
    ) -> None:
        nodes = AdvancedReasoningNodes(
            llm_client,
            tool_registry,
            max_subtasks=max_subtasks,
            max_tool_calls=max_tool_calls,
            max_replans=max_replans,
        )
        self._graph = build_advanced_reasoning_graph(nodes)

    @classmethod
    def from_flags(
        cls,
        llm_client: LLMClient,
        tool_registry: AdvancedToolRegistry,
        flags: ReasoningFeatureFlags,
    ) -> "AdvancedReasoningPlanner":
        return cls(
            llm_client,
            tool_registry,
            max_subtasks=flags.deep_agent_max_subtasks,
            max_tool_calls=flags.deep_agent_max_subtasks,
            max_replans=1,
        )

    @property
    def graph(self) -> CompiledStateGraph:
        return self._graph

    def run(
        self,
        safe_question: str,
        supervisor_decision: SupervisorDecision,
    ) -> AdvancedReasoningResult:
        if not safe_question.strip():
            raise AdvancedReasoningPlanError("A privacy-safe question is required")
        output = self._graph.invoke(
            {
                "safe_question": safe_question,
                "supervisor_route": supervisor_decision.route,
                "warnings": (),
            }
        )
        synthesis = output["final_synthesis"]
        return AdvancedReasoningResult(
            answer=synthesis.answer,
            tool_results=output["tool_results"],
            citations=synthesis.citation_ids,
            warnings=output.get("warnings", ()),
        )
