"""Tests for typed internal route and confidence contracts."""

import pytest
from pydantic import ValidationError

from app.core.chat_modes import ChatModeKey, chat_mode_registry
from app.core.config import Settings
from app.routing.models import (
    InternalRoute,
    LLMIntentDecision,
    RoutingSource,
    SupervisorDecision,
)

EXPECTED_INTERNAL_ROUTES = [
    "group_access",
    "sql",
    "forecasting",
    "chat",
    "help",
    "data_discovery",
    "knowledge_catalog",
    "semantica",
    "data_quality",
]


def test_internal_route_enum_is_exact_and_does_not_include_auto() -> None:
    assert [route.value for route in InternalRoute] == EXPECTED_INTERNAL_ROUTES
    assert "auto" not in {route.value for route in InternalRoute}


def test_internal_only_routes_do_not_change_top_level_chat_modes() -> None:
    top_level_modes = [mode.key.value for mode in chat_mode_registry.list_modes()]

    assert "forecasting" not in top_level_modes
    assert "chat" not in top_level_modes
    assert "help" not in top_level_modes
    assert top_level_modes == [
        "auto",
        "sql",
        "group_access",
        "data_discovery",
        "knowledge_catalog",
        "semantica",
        "data_quality",
    ]


@pytest.mark.parametrize("confidence", [-0.01, 1.01])
def test_llm_decision_rejects_out_of_range_confidence(confidence: float) -> None:
    with pytest.raises(ValidationError):
        LLMIntentDecision(intent=InternalRoute.SQL, confidence=confidence)


@pytest.mark.parametrize("confidence", [-0.01, 1.01])
def test_supervisor_decision_rejects_out_of_range_confidence(confidence: float) -> None:
    with pytest.raises(ValidationError):
        SupervisorDecision(
            route=InternalRoute.SQL,
            confidence=confidence,
            source=RoutingSource.LLM,
            selected_mode=ChatModeKey.AUTO,
        )


def test_intent_router_threshold_defaults_and_validates_bounds() -> None:
    assert Settings(_env_file=None).intent_router_min_confidence == 0.60
    with pytest.raises(ValidationError):
        Settings(_env_file=None, intent_router_min_confidence=-0.01)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, intent_router_min_confidence=1.01)
