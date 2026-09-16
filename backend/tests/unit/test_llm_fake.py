"""Tests for the deterministic network-free LLM fake."""

from app.llm.base import LLMClient
from app.llm.models import LLMMessage, LLMRequest, LLMRole
from tests.llm.fakes import FakeLLMClient, FakeStructuredAnswer


def test_fake_client_satisfies_contract_and_returns_deterministic_results() -> None:
    client = FakeLLMClient(
        text="fixed text",
        structured_payload={"answer": "fixed structured value"},
    )
    request = LLMRequest(messages=[LLMMessage(role=LLMRole.USER, content="Harmless test")])

    text_response = client.generate(request)
    structured_response = client.generate_structured(request, FakeStructuredAnswer)

    assert isinstance(client, LLMClient)
    assert text_response.text == "fixed text"
    assert text_response.provider == "test_fake"
    assert structured_response == FakeStructuredAnswer(answer="fixed structured value")
    assert client.requests == [request, request]
