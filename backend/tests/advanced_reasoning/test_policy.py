"""Deterministic promotion-policy coverage."""

from app.advanced_reasoning.models import ReasoningExecutionMode
from app.advanced_reasoning.policy import ReasoningPromotionPolicy
from app.routing.models import InternalRoute
from tests.advanced_reasoning.helpers import (
    RecordingTool,
    reasoning_flags,
    supervisor_decision,
    tool_registry,
)
from tests.routing.helpers import make_registry


def _decide(*, flags=None, registry=None, tools=None, decision=None):
    agent_registry = registry or make_registry()
    available_tools = tools or tool_registry(
        RecordingTool("sql", InternalRoute.SQL, []),
    )
    return ReasoningPromotionPolicy(
        flags or reasoning_flags(),
        agent_registry,
        available_tools,
    ).decide(decision or supervisor_decision())


def test_disabled_promotion_is_standard() -> None:
    assert (
        _decide(flags=reasoning_flags(deep_agent_single_intent_enabled=False))
        is ReasoningExecutionMode.STANDARD
    )


def test_low_confidence_is_standard() -> None:
    assert _decide(decision=supervisor_decision(confidence=0.79)) is ReasoningExecutionMode.STANDARD


def test_ineligible_route_is_standard() -> None:
    assert (
        _decide(decision=supervisor_decision(route=InternalRoute.DATA_QUALITY))
        is ReasoningExecutionMode.STANDARD
    )


def test_disabled_agent_is_standard() -> None:
    registry = make_registry(sql=False)
    tools = tool_registry(RecordingTool("sql", InternalRoute.SQL, []))
    assert _decide(registry=registry, tools=tools) is ReasoningExecutionMode.STANDARD


def test_missing_tool_implementation_is_standard() -> None:
    assert _decide(tools=tool_registry()) is ReasoningExecutionMode.STANDARD


def test_all_requirements_promote_without_llm() -> None:
    assert _decide() is ReasoningExecutionMode.ADVANCED
