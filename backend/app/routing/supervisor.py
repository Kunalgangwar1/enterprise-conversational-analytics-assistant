"""Routing-only supervisor policy; specialist execution is intentionally absent."""

from types import MappingProxyType

from app.core.chat_modes import ChatModeKey
from app.core.config import get_settings
from app.routing.exceptions import RoutingConfigurationError, RoutingUnavailableError
from app.routing.heuristics import detect_forecasting_intent, route_by_heuristic
from app.routing.intent_router import IntentRouterAgent
from app.routing.models import InternalRoute, RoutingSource, SupervisorDecision
from app.routing.registry import AgentRegistry, get_agent_registry

_EXPLICIT_ROUTES = MappingProxyType(
    {
        ChatModeKey.GROUP_ACCESS: InternalRoute.GROUP_ACCESS,
        ChatModeKey.DATA_DISCOVERY: InternalRoute.DATA_DISCOVERY,
        ChatModeKey.KNOWLEDGE_CATALOG: InternalRoute.KNOWLEDGE_CATALOG,
        ChatModeKey.SEMANTICA: InternalRoute.SEMANTICA,
        ChatModeKey.DATA_QUALITY: InternalRoute.DATA_QUALITY,
    }
)


class SupervisorMultiAgent:
    """Select an enabled internal route without invoking any specialist."""

    def __init__(
        self,
        intent_router: IntentRouterAgent,
        *,
        agent_registry: AgentRegistry | None = None,
        min_confidence: float | None = None,
    ) -> None:
        self._intent_router = intent_router
        self._agent_registry = agent_registry or get_agent_registry()
        self._min_confidence = (
            get_settings().intent_router_min_confidence
            if min_confidence is None
            else min_confidence
        )
        if not 0 <= self._min_confidence <= 1:
            raise RoutingConfigurationError(
                "Intent-router confidence threshold must be between 0 and 1"
            )

    def route(self, safe_text: str, selected_mode: ChatModeKey) -> SupervisorDecision:
        """Apply explicit-mode or auto-mode routing to privacy-processed text."""

        if selected_mode is ChatModeKey.AUTO:
            return self._route_auto(safe_text)
        return self._route_explicit(safe_text, selected_mode)

    def _route_explicit(
        self,
        safe_text: str,
        selected_mode: ChatModeKey,
    ) -> SupervisorDecision:
        if selected_mode is ChatModeKey.SQL:
            self._agent_registry.require_enabled(InternalRoute.SQL)
            forecast = detect_forecasting_intent(safe_text)
            if forecast is not None and self._agent_registry.is_enabled(InternalRoute.FORECASTING):
                return SupervisorDecision(
                    route=InternalRoute.FORECASTING,
                    confidence=forecast.confidence,
                    source=RoutingSource.HEURISTIC,
                    selected_mode=selected_mode,
                    reason_code=forecast.reason_code,
                )
            reason_code = (
                "forecasting_disabled_use_sql" if forecast is not None else "explicit_mode"
            )
            return SupervisorDecision(
                route=InternalRoute.SQL,
                confidence=1.0,
                source=RoutingSource.FORCED_MODE,
                selected_mode=selected_mode,
                reason_code=reason_code,
            )

        try:
            route = _EXPLICIT_ROUTES[selected_mode]
        except KeyError as exc:
            raise RoutingConfigurationError(
                "Selected chat mode has no explicit routing policy"
            ) from exc
        self._agent_registry.require_enabled(route)
        return SupervisorDecision(
            route=route,
            confidence=1.0,
            source=RoutingSource.FORCED_MODE,
            selected_mode=selected_mode,
            reason_code="explicit_mode",
        )

    def _route_auto(self, safe_text: str) -> SupervisorDecision:
        heuristic = route_by_heuristic(safe_text)
        if heuristic is not None:
            if self._agent_registry.is_enabled(heuristic.route):
                return SupervisorDecision(
                    route=heuristic.route,
                    confidence=heuristic.confidence,
                    source=RoutingSource.HEURISTIC,
                    selected_mode=ChatModeKey.AUTO,
                    reason_code=heuristic.reason_code,
                )
            return self._knowledge_catalog_fallback("heuristic_route_disabled")

        llm_decision = self._intent_router.classify(safe_text)
        if llm_decision.confidence < self._min_confidence:
            return self._knowledge_catalog_fallback("low_confidence")
        if not self._agent_registry.is_enabled(llm_decision.intent):
            return self._knowledge_catalog_fallback("llm_route_disabled")
        return SupervisorDecision(
            route=llm_decision.intent,
            confidence=llm_decision.confidence,
            source=RoutingSource.LLM,
            selected_mode=ChatModeKey.AUTO,
            reason_code="structured_classification",
        )

    def _knowledge_catalog_fallback(self, reason_code: str) -> SupervisorDecision:
        if not self._agent_registry.is_enabled(InternalRoute.KNOWLEDGE_CATALOG):
            raise RoutingUnavailableError(
                "No enabled route is available for the supervisor fallback policy"
            )
        return SupervisorDecision(
            route=InternalRoute.KNOWLEDGE_CATALOG,
            confidence=0.0,
            source=RoutingSource.FALLBACK,
            selected_mode=ChatModeKey.AUTO,
            reason_code=reason_code,
        )
