"""Deterministic advanced-tool and policy helpers."""

from app.advanced_reasoning.models import ToolExecutionResult, ToolExecutionStatus
from app.advanced_reasoning.tools import AdvancedToolRegistry
from app.core.chat_modes import ChatModeKey
from app.core.feature_flags import ReasoningFeatureFlags
from app.routing.models import InternalRoute, RoutingSource, SupervisorDecision
from tests.routing.helpers import make_registry


class RecordingTool:
    description = "Deterministic test application tool."

    def __init__(self, name: str, route: InternalRoute, calls: list[str]) -> None:
        self.name = name
        self.route = route
        self.calls = calls

    def execute(self, instruction: str) -> ToolExecutionResult:
        self.calls.append(self.name)
        return ToolExecutionResult(
            step_id="pending",
            tool_name=self.name,
            status=ToolExecutionStatus.SUCCESS,
            summary=f"Completed {instruction}",
            citations=(f"citation-{self.name}",),
        )


def reasoning_flags(**overrides: object) -> ReasoningFeatureFlags:
    values = {
        "deep_agent_single_intent_enabled": True,
        "deep_agent_min_confidence": 0.8,
        "deep_agent_eligible_routes": ["sql", "knowledge_catalog"],
        "deep_agent_max_subtasks": 5,
        "nlp2sql_multihop_enabled": False,
        "nlp2sql_multihop_max_hops": 3,
        "nlp2sql_multihop_max_rows_per_hop": 100,
        "nlp2sql_multihop_total_row_budget": 250,
        "nlp2sql_multihop_total_timeout_seconds": 20,
    }
    values.update(overrides)
    return ReasoningFeatureFlags.model_validate(values)


def supervisor_decision(
    *, route: InternalRoute = InternalRoute.SQL, confidence: float = 0.9
) -> SupervisorDecision:
    return SupervisorDecision(
        route=route,
        confidence=confidence,
        source=RoutingSource.LLM,
        selected_mode=ChatModeKey.AUTO,
    )


def tool_registry(
    *tools: RecordingTool,
    enabled_names: set[str] | None = None,
    **agent_overrides: bool,
) -> AdvancedToolRegistry:
    return AdvancedToolRegistry(
        tools,
        agent_registry=make_registry(**agent_overrides),
        enabled_tool_names=enabled_names,
    )
