from __future__ import annotations

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from pydantic import BaseModel

from app.core.config import Settings
from app.llm.models import LLMMessage, LLMRequest, LLMResponse, LLMRole, LLMUsage
from app.observability import instrumentation
from app.observability.instrumentation import ObservabilityRuntime, initialize_observability
from app.observability.llm import InstrumentedLLMClient
from app.observability.metrics import set_metrics
from app.observability.tracing import safe_span_attributes, set_tracer, start_span


class RecordingMetrics:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int | float, dict[str, object]]] = []

    def record(
        self, name: str, value: int | float = 1, attributes: dict[str, object] | None = None
    ) -> None:
        self.calls.append((name, value, attributes or {}))


class StructuredAnswer(BaseModel):
    answer: str


class FakeLLM:
    def generate(self, request: LLMRequest) -> LLMResponse:
        return LLMResponse(
            text="response secret",
            provider="gemini",
            model="model-1",
            usage=LLMUsage(input_tokens=7, output_tokens=3),
            elapsed_ms=1,
        )

    def generate_structured(
        self, request: LLMRequest, response_model: type[StructuredAnswer]
    ) -> StructuredAnswer:
        return response_model(answer="private structured response")


def _tracing() -> tuple[TracerProvider, InMemorySpanExporter]:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    set_tracer(provider.get_tracer("phase27-tests"))
    return provider, exporter


def _settings(**overrides: object) -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        observability_enabled=True,
        **overrides,
    )


def test_safe_span_attributes_drop_content_and_identity() -> None:
    result = safe_span_attributes(
        {
            "operation.name": "generate",
            "prompt": "member has diagnosis",
            "db.statement": "SELECT * FROM members",
            "session_id": "session-secret",
            "redis.key": "redis-secret",
            "retrieved.chunk": "private evidence",
        }
    )
    assert result == {"operation.name": "generate"}


def test_sql_retrieval_and_session_spans_exclude_sensitive_values() -> None:
    provider, exporter = _tracing()
    with start_span(
        "db.query",
        {
            "db.system": "postgresql",
            "db.operation.name": "select",
            "db.statement": "SELECT member_id FROM claims",
        },
    ):
        pass
    with start_span(
        "retrieval.search",
        {"retriever_type": "knowledge_catalog", "retrieved.chunk": "private chunk"},
    ):
        pass
    with start_span(
        "session.load",
        {"session.operation": "load", "redis.key": "eca:secret-session"},
    ):
        pass
    serialized = repr([span.attributes for span in exporter.get_finished_spans()])
    assert "SELECT" not in serialized
    assert "private chunk" not in serialized
    assert "secret-session" not in serialized
    provider.shutdown()


def test_unexpected_exception_span_is_sanitized() -> None:
    provider, exporter = _tracing()
    with pytest.raises(RuntimeError, match="postgresql"):
        with start_span("operation"):
            raise RuntimeError("postgresql://user:password@host/private")
    span = exporter.get_finished_spans()[0]
    assert span.status.is_ok is False
    assert span.attributes["error.type"] == "RuntimeError"
    assert "password" not in repr(span.events)
    provider.shutdown()


def test_llm_metrics_and_span_exclude_prompt_and_response() -> None:
    provider, exporter = _tracing()
    metrics = RecordingMetrics()
    set_metrics(metrics)  # type: ignore[arg-type]
    client = InstrumentedLLMClient(FakeLLM(), provider="gemini", model="model-1")
    request = LLMRequest(
        messages=[LLMMessage(role=LLMRole.USER, content="member 123 private diagnosis")]
    )
    response = client.generate(request)
    assert response.text == "response secret"
    serialized = repr(metrics.calls) + repr(exporter.get_finished_spans()[0].attributes)
    assert "member 123" not in serialized
    assert "response secret" not in serialized
    assert "prompt" not in serialized
    assert {name for name, _, _ in metrics.calls} >= {
        "llm.requests",
        "llm.duration",
        "llm.tokens.input",
        "llm.tokens.output",
    }
    provider.shutdown()


def test_structured_llm_response_content_is_not_captured() -> None:
    provider, exporter = _tracing()
    metrics = RecordingMetrics()
    set_metrics(metrics)  # type: ignore[arg-type]
    client = InstrumentedLLMClient(FakeLLM(), provider="gemini", model="model-1")
    request = LLMRequest(messages=[LLMMessage(role=LLMRole.USER, content="private prompt")])
    client.generate_structured(request, StructuredAnswer)
    serialized = repr(metrics.calls) + repr(exporter.get_finished_spans()[0].attributes)
    assert "private prompt" not in serialized
    assert "private structured response" not in serialized
    provider.shutdown()


def test_disabled_observability_needs_no_endpoint() -> None:
    runtime = initialize_observability(
        Settings(_env_file=None, app_env="test", observability_enabled=False),
        configure_logs=False,
    )
    assert runtime.tracer_provider is None
    assert runtime.meter_provider is None
    runtime.shutdown()


def test_initialization_failure_is_fail_open(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(_settings: object) -> object:
        raise OSError("collector unavailable with Bearer secret")

    monkeypatch.setattr(instrumentation, "_span_exporter", fail)
    runtime = initialize_observability(
        _settings(otel_exporter_otlp_endpoint="http://127.0.0.1:4318"),
        configure_logs=False,
    )
    assert runtime.tracer_provider is None
    assert runtime.meter_provider is None


class ProviderSpy:
    def __init__(self, *, fail: bool = False) -> None:
        self.flush_timeouts: list[int] = []
        self.shutdown_timeouts: list[int | None] = []
        self.fail = fail

    def force_flush(self, *, timeout_millis: int) -> None:
        self.flush_timeouts.append(timeout_millis)
        if self.fail:
            raise OSError("unavailable")

    def shutdown(self, timeout_millis: int | None = None) -> None:
        self.shutdown_timeouts.append(timeout_millis)
        if self.fail:
            raise OSError("unavailable")


def test_runtime_flush_and_shutdown_are_bounded() -> None:
    trace_provider = ProviderSpy()
    meter_provider = ProviderSpy()
    runtime = ObservabilityRuntime(
        tracer_provider=trace_provider,  # type: ignore[arg-type]
        meter_provider=meter_provider,  # type: ignore[arg-type]
        export_timeout_seconds=2.5,
    )
    runtime.shutdown()
    assert trace_provider.flush_timeouts == [2_500]
    assert meter_provider.flush_timeouts == [2_500]
    assert trace_provider.shutdown_timeouts == [None]
    assert meter_provider.shutdown_timeouts == [2_500]


def test_runtime_exporter_failures_do_not_escape() -> None:
    provider = ProviderSpy(fail=True)
    runtime = ObservabilityRuntime(
        tracer_provider=provider,  # type: ignore[arg-type]
        export_timeout_seconds=1,
    )
    runtime.shutdown()
    assert provider.flush_timeouts == [1_000]
    assert provider.shutdown_timeouts == [None]


def test_unsafe_otlp_endpoints_are_rejected() -> None:
    endpoints = [
        "ftp://collector:4318",
        "http://user:password@collector:4318",
        "http://collector:4318?token=secret",
        "http://collector:4318/#fragment",
    ]
    for endpoint in endpoints:
        with pytest.raises(ValueError, match="safe HTTP"):
            _settings(otel_exporter_otlp_endpoint=endpoint)


def test_signal_endpoint_adds_only_expected_signal_path() -> None:
    assert instrumentation._signal_endpoint("http://collector:4318", "traces") == (
        "http://collector:4318/v1/traces"
    )
    assert instrumentation._signal_endpoint("http://collector:4318/v1/metrics", "metrics") == (
        "http://collector:4318/v1/metrics"
    )
