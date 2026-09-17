from __future__ import annotations

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

import app.llm.factory as llm_factory
from app.core.config import Settings
from app.llm.models import LLMMessage, LLMRequest, LLMResponse, LLMRole
from app.observability.tracing import set_tracer
from app.reliability.circuit_breaker import CircuitBreaker, CircuitBreakerConfig
from app.reliability.clients import (
    FallbackLLMClient,
    ResilientEmbeddingClient,
    ResilientLLMClient,
)
from app.reliability.errors import (
    ProviderRequestError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from app.reliability.policy import RetryPolicy, RetryPolicyConfig
from app.reliability.resources import close_provider_resources, register_provider_resource


def _request() -> LLMRequest:
    return LLMRequest(
        messages=[LLMMessage(role=LLMRole.USER, content="private prompt must not enter telemetry")]
    )


def _response(text: str = "safe result") -> LLMResponse:
    return LLMResponse(
        text=text,
        provider="gemini",
        model="test-model",
        elapsed_ms=1,
    )


def _policy(*, attempts: int = 2) -> RetryPolicy:
    return RetryPolicy(
        RetryPolicyConfig(
            max_attempts=attempts,
            initial_delay_seconds=0.001,
            max_delay_seconds=0.001,
            max_total_delay_seconds=0.01,
            jitter_ratio=0,
            operation_timeout_seconds=2,
            request_timeout_seconds=1,
        ),
        circuit_breaker=CircuitBreaker(CircuitBreakerConfig(enabled=False)),
        sleeper=lambda _delay: None,
    )


class FakeLLM:
    def __init__(self, outcomes: list[object]) -> None:
        self.outcomes = outcomes
        self.calls = 0
        self.close_calls = 0

    def generate(self, request: LLMRequest) -> LLMResponse:
        del request
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome  # type: ignore[return-value]

    def generate_structured(self, request: LLMRequest, response_model: type):
        del request, response_model
        return self.generate(_request())

    def close(self) -> None:
        self.close_calls += 1


class FakeEmbedding:
    provider_name = "gemini"
    model_name = "embedding-model"
    dimensions = 2

    def __init__(self) -> None:
        self.calls = 0
        self.closed = False

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self.calls += 1
        if self.calls == 1:
            raise ProviderTimeoutError("timeout")
        return [[1.0, 0.0] for _ in texts]

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]

    def close(self) -> None:
        self.closed = True


def test_embedding_calls_use_the_retry_policy() -> None:
    raw = FakeEmbedding()
    client = ResilientEmbeddingClient(raw, provider="gemini", policy=_policy())
    assert client.embed_query("private query") == [1.0, 0.0]
    assert raw.calls == 2


def test_fallback_is_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    primary = FakeLLM([_response()])
    monkeypatch.setattr(llm_factory, "_create_provider_client", lambda settings, provider: primary)
    client = llm_factory.create_llm_client(Settings(_env_file=None, gemini_api_key="test-key"))
    assert client is primary
    assert not isinstance(client, FallbackLLMClient)


def test_explicit_fallback_handles_only_transient_primary_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    primary = FakeLLM([ProviderTimeoutError("timeout")])
    fallback = FakeLLM([_response("fallback result")])
    monkeypatch.setattr(
        llm_factory,
        "_create_provider_client",
        lambda settings, provider: primary if provider == "gemini" else fallback,
    )
    client = llm_factory.create_llm_client(
        Settings(
            _env_file=None,
            gemini_api_key="test-key",
            azure_openai_endpoint="https://example.openai.azure.com/",
            azure_openai_api_key="test-key",
            azure_openai_deployment="fallback-deployment",
            llm_fallback_provider="azure_openai",
        )
    )
    assert client.generate(_request()).text == "fallback result"
    assert primary.calls == fallback.calls == 1


def test_single_retry_owner_prevents_nested_attempt_multiplication() -> None:
    raw = FakeLLM([ProviderUnavailableError("503") for _ in range(3)])
    client = ResilientLLMClient(raw, provider="gemini", policy=_policy(attempts=3))

    with pytest.raises(ProviderUnavailableError):
        client.generate(_request())

    assert raw.calls == 3


def test_explicit_fallback_is_one_hop_with_independent_bounded_attempts() -> None:
    primary_raw = FakeLLM([ProviderUnavailableError("503") for _ in range(2)])
    fallback_raw = FakeLLM([ProviderTimeoutError("timeout"), _response("recovered")])
    primary = ResilientLLMClient(primary_raw, provider="gemini", policy=_policy(attempts=2))
    fallback = ResilientLLMClient(
        fallback_raw,
        provider="azure_openai",
        policy=_policy(attempts=2),
    )
    client = FallbackLLMClient(primary, fallback, fallback_provider="azure_openai")

    assert client.generate(_request()).text == "recovered"
    assert primary_raw.calls == 2
    assert fallback_raw.calls == 2


def test_fallback_does_not_hide_deterministic_request_failure() -> None:
    primary = FakeLLM([ProviderRequestError("request rejected")])
    fallback = FakeLLM([_response("must not be used")])
    client = FallbackLLMClient(primary, fallback, fallback_provider="azure_openai")
    with pytest.raises(ProviderRequestError):
        client.generate(_request())
    assert fallback.calls == 0


def test_resilience_spans_exclude_prompt_response_and_keys() -> None:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    set_tracer(provider.get_tracer("phase28-tests"))
    raw = FakeLLM([ProviderTimeoutError("safe timeout"), _response("private response")])
    client = ResilientLLMClient(raw, provider="gemini", policy=_policy())
    assert client.generate(_request()).text == "private response"
    serialized = repr(exporter.get_finished_spans()[0].attributes)
    assert "private prompt" not in serialized
    assert "private response" not in serialized
    assert "api_key" not in serialized
    assert "retry_count" in serialized
    provider.shutdown()
    set_tracer(None)


def test_close_cascades_to_provider_resources() -> None:
    raw = FakeLLM([_response()])
    client = register_provider_resource(
        ResilientLLMClient(raw, provider="gemini", policy=_policy())
    )
    close_provider_resources()
    assert raw.close_calls == 1
    client.close()
    assert raw.close_calls == 1


def test_embedding_wrapper_preserves_manifest_metadata() -> None:
    raw = FakeEmbedding()
    client = ResilientEmbeddingClient(raw, provider="gemini", policy=_policy())
    assert (client.provider_name, client.model_name, client.dimensions) == (
        "gemini",
        "embedding-model",
        2,
    )


def test_invalid_reliability_configuration_fails_fast() -> None:
    with pytest.raises(ValueError, match="CONNECT_TIMEOUT"):
        Settings(
            _env_file=None,
            llm_connect_timeout_seconds=20,
            llm_timeout_seconds=10,
        )
    with pytest.raises(ValueError, match="FALLBACK_PROVIDER"):
        Settings(
            _env_file=None,
            llm_provider="gemini",
            llm_fallback_provider="gemini",
        )
