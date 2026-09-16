"""Deterministic promotion from normal specialist routing to deep reasoning."""

from app.advanced_reasoning.models import ReasoningExecutionMode
from app.advanced_reasoning.tools import AdvancedToolRegistry
from app.core.feature_flags import ReasoningFeatureFlags
from app.routing.models import SupervisorDecision
from app.routing.registry import AgentRegistry


class ReasoningPromotionPolicy:
    """Apply feature, confidence, route, registry, and implementation gates."""

    def __init__(
        self,
        flags: ReasoningFeatureFlags,
        agent_registry: AgentRegistry,
        tool_registry: AdvancedToolRegistry,
    ) -> None:
        self._flags = flags
        self._agent_registry = agent_registry
        self._tool_registry = tool_registry

    def decide(self, decision: SupervisorDecision) -> ReasoningExecutionMode:
        if not self._flags.deep_agent_single_intent_enabled:
            return ReasoningExecutionMode.STANDARD
        if decision.confidence < self._flags.deep_agent_min_confidence:
            return ReasoningExecutionMode.STANDARD
        if decision.route.value not in self._flags.deep_agent_eligible_routes:
            return ReasoningExecutionMode.STANDARD
        if not self._agent_registry.is_enabled(decision.route):
            return ReasoningExecutionMode.STANDARD
        if not self._tool_registry.has_route(decision.route):
            return ReasoningExecutionMode.STANDARD
        return ReasoningExecutionMode.ADVANCED
