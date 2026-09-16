"""Tests for explicit and automatic supervisor routing policy."""

import pytest

from app.core.chat_modes import ChatModeKey
from app.routing.exceptions import RoutingUnavailableError
from app.routing.intent_router import IntentRouterAgent
from app.routing.models import InternalRoute, RoutingSource
from app.routing.supervisor import SupervisorMultiAgent
from tests.llm.fakes import FakeLLMClient
from tests.routing.helpers import make_registry


def _supervisor(
    fake: FakeLLMClient,
    *,
    min_confidence: float = 0.60,
    **availability: bool,
) -> SupervisorMultiAgent:
    return SupervisorMultiAgent(
        IntentRouterAgent(fake),
        agent_registry=make_registry(**availability),
        min_confidence=min_confidence,
    )


@pytest.mark.parametrize(
    ("selected_mode", "expected_route"),
    [
        (ChatModeKey.GROUP_ACCESS, InternalRoute.GROUP_ACCESS),
        (ChatModeKey.DATA_DISCOVERY, InternalRoute.DATA_DISCOVERY),
        (ChatModeKey.KNOWLEDGE_CATALOG, InternalRoute.KNOWLEDGE_CATALOG),
        (ChatModeKey.SEMANTICA, InternalRoute.SEMANTICA),
        (ChatModeKey.DATA_QUALITY, InternalRoute.DATA_QUALITY),
    ],
)
def test_explicit_non_auto_modes_bypass_general_llm_classifier(
    selected_mode: ChatModeKey,
    expected_route: InternalRoute,
) -> None:
    fake = FakeLLMClient()

    decision = _supervisor(fake).route("Any privacy-safe content", selected_mode)

    assert decision.route is expected_route
    assert decision.source is RoutingSource.FORCED_MODE
    assert fake.requests == []


def test_explicit_sql_normally_routes_to_sql_without_llm() -> None:
    fake = FakeLLMClient()

    decision = _supervisor(fake).route("Show claims from 2026.", ChatModeKey.SQL)

    assert decision.route is InternalRoute.SQL
    assert decision.source is RoutingSource.FORCED_MODE
    assert fake.requests == []


def test_explicit_sql_forecasting_subroute_bypasses_llm() -> None:
    fake = FakeLLMClient()

    decision = _supervisor(fake).route(
        "Forecast paid claims next quarter.",
        ChatModeKey.SQL,
    )

    assert decision.route is InternalRoute.FORECASTING
    assert decision.source is RoutingSource.HEURISTIC
    assert fake.requests == []


def test_disabled_explicit_mode_raises_without_silent_fallback() -> None:
    fake = FakeLLMClient()

    with pytest.raises(RoutingUnavailableError, match="semantica"):
        _supervisor(fake, semantica=False).route("Use Semantica", ChatModeKey.SEMANTICA)

    assert fake.requests == []


def test_disabled_forecasting_subroute_falls_back_to_enabled_sql() -> None:
    fake = FakeLLMClient()

    decision = _supervisor(fake, forecasting=False).route(
        "Forecast paid claims next quarter.",
        ChatModeKey.SQL,
    )

    assert decision.route is InternalRoute.SQL
    assert decision.source is RoutingSource.FORCED_MODE
    assert decision.reason_code == "forecasting_disabled_use_sql"
    assert fake.requests == []


def test_auto_heuristic_route_does_not_call_llm() -> None:
    fake = FakeLLMClient()

    decision = _supervisor(fake).route(
        "How can I request access to the claims dataset?",
        ChatModeKey.AUTO,
    )

    assert decision.route is InternalRoute.GROUP_ACCESS
    assert decision.source is RoutingSource.HEURISTIC
    assert fake.requests == []


@pytest.mark.parametrize(
    ("intent", "expected_route"),
    [
        ("sql", InternalRoute.SQL),
        ("knowledge_catalog", InternalRoute.KNOWLEDGE_CATALOG),
    ],
)
def test_ambiguous_auto_request_accepts_high_confidence_structured_llm_route(
    intent: str,
    expected_route: InternalRoute,
) -> None:
    fake = FakeLLMClient(structured_payload={"intent": intent, "confidence": 0.95})

    decision = _supervisor(fake).route(
        "Show total paid claims by specialty.",
        ChatModeKey.AUTO,
    )

    assert decision.route is expected_route
    assert decision.confidence == 0.95
    assert decision.source is RoutingSource.LLM
    assert len(fake.requests) == 1


def test_low_confidence_llm_result_falls_back_to_knowledge_catalog() -> None:
    fake = FakeLLMClient(structured_payload={"intent": "sql", "confidence": 0.59})

    decision = _supervisor(fake).route("An uncertain request", ChatModeKey.AUTO)

    assert decision.route is InternalRoute.KNOWLEDGE_CATALOG
    assert decision.source is RoutingSource.FALLBACK
    assert decision.reason_code == "low_confidence"
    assert decision.confidence == 0.0


def test_disabled_llm_selected_route_falls_back_to_enabled_knowledge_catalog() -> None:
    fake = FakeLLMClient(structured_payload={"intent": "semantica", "confidence": 0.95})

    decision = _supervisor(fake, semantica=False).route(
        "An ambiguous semantic request",
        ChatModeKey.AUTO,
    )

    assert decision.route is InternalRoute.KNOWLEDGE_CATALOG
    assert decision.source is RoutingSource.FALLBACK
    assert decision.reason_code == "llm_route_disabled"


def test_no_enabled_knowledge_catalog_fallback_raises_controlled_error() -> None:
    fake = FakeLLMClient(structured_payload={"intent": "semantica", "confidence": 0.95})

    with pytest.raises(RoutingUnavailableError, match="fallback policy"):
        _supervisor(fake, semantica=False, knowledge_catalog=False).route(
            "An ambiguous semantic request",
            ChatModeKey.AUTO,
        )
