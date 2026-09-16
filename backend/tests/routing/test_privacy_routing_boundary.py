"""Composition tests for privacy preprocessing before supervisor classification."""

from app.core.chat_modes import ChatModeKey
from app.llm.models import LLMRole
from app.privacy import PrivacyProcessor
from app.routing import IntentRouterAgent, SupervisorMultiAgent
from app.routing.models import InternalRoute
from tests.llm.fakes import FakeLLMClient
from tests.routing.helpers import make_registry


def test_privacy_processed_text_reaches_supervisor_llm_classifier() -> None:
    original = "Show claims for M000245 and alice@example.com"
    privacy_result = PrivacyProcessor().process(original)
    fake = FakeLLMClient(structured_payload={"intent": "sql", "confidence": 0.95})
    supervisor = SupervisorMultiAgent(
        IntentRouterAgent(fake),
        agent_registry=make_registry(),
        min_confidence=0.60,
    )

    decision = supervisor.route(privacy_result.safe_text, ChatModeKey.AUTO)

    assert decision.route is InternalRoute.SQL
    classifier_input = fake.requests[0].messages[-1]
    assert classifier_input.role is LLMRole.USER
    assert "T001" in classifier_input.content
    assert "[EMAIL]" in classifier_input.content
    assert "M000245" not in classifier_input.content
    assert "alice@example.com" not in classifier_input.content
