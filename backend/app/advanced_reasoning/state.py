"""Privacy-safe LangGraph state for generic advanced reasoning."""

from typing import TypedDict

from app.advanced_reasoning.models import (
    AdvancedSynthesis,
    ReasoningDecomposition,
    ReflectionDecision,
    ToolExecutionResult,
    ToolPlan,
)
from app.routing.models import InternalRoute


class AdvancedReasoningState(TypedDict, total=False):
    safe_question: str
    supervisor_route: InternalRoute
    decomposition: ReasoningDecomposition
    tool_plan: ToolPlan
    current_step: int
    tool_results: tuple[ToolExecutionResult, ...]
    reflection_decision: ReflectionDecision
    reflection_count: int
    final_synthesis: AdvancedSynthesis
    warnings: tuple[str, ...]
