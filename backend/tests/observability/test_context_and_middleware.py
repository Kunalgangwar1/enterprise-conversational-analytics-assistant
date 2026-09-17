from __future__ import annotations

import asyncio
from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from app.observability.context import bind_context, correlation_fields, current_context
from app.observability.instrumentation import ObservabilityRuntime
from app.observability.metrics import set_metrics
from app.observability.middleware import (
    ObservabilityMiddleware,
    _bounded_method,
    _resolve_request_id,
)
from app.observability.tracing import set_tracer


class RecordingMetrics:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int | float, dict[str, object]]] = []

    def record(
        self, name: str, value: int | float = 1, attributes: dict[str, object] | None = None
    ) -> None:
        self.calls.append((name, value, attributes or {}))


@pytest.fixture
def instrumented_client() -> Iterator[tuple[TestClient, RecordingMetrics, InMemorySpanExporter]]:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    set_tracer(provider.get_tracer("phase27-tests"))
    metrics = RecordingMetrics()
    set_metrics(metrics)  # type: ignore[arg-type]
    app = FastAPI()

    @app.get("/items/{item_id}")
    async def item(item_id: str) -> dict[str, str]:
        assert current_context().request_id
        return {"item": item_id}

    app.add_middleware(ObservabilityMiddleware, runtime=ObservabilityRuntime(provider, None))
    with TestClient(app) as client:
        yield client, metrics, exporter
    provider.shutdown()


def test_request_id_is_generated_and_returned(instrumented_client: tuple[object, ...]) -> None:
    client = instrumented_client[0]
    assert isinstance(client, TestClient)
    response = client.get("/items/42")
    assert len(response.headers["x-request-id"]) == 32
    assert response.headers["x-request-id"].isalnum()


def test_valid_request_id_is_preserved(instrumented_client: tuple[object, ...]) -> None:
    client = instrumented_client[0]
    assert isinstance(client, TestClient)
    response = client.get("/items/42", headers={"X-Request-Id": "safe_ID-27.1"})
    assert response.headers["x-request-id"] == "safe_ID-27.1"


@pytest.mark.parametrize(
    "candidate",
    ["", "contains spaces", "/unsafe", "ümlaut", "x" * 65],
)
def test_invalid_request_ids_are_replaced(candidate: str) -> None:
    replacement = _resolve_request_id(candidate)
    assert replacement != candidate
    assert len(replacement) == 32


def test_http_metrics_use_route_template_not_raw_identifier(
    instrumented_client: tuple[TestClient, RecordingMetrics, InMemorySpanExporter],
) -> None:
    client, metrics, _ = instrumented_client
    client.get("/items/private-member-123")
    request_call = next(call for call in metrics.calls if call[0] == "http.server.requests")
    assert request_call[2]["route"] == "/items/{item_id}"
    assert "private-member-123" not in repr(metrics.calls)


def test_active_request_counter_returns_to_zero(
    instrumented_client: tuple[TestClient, RecordingMetrics, InMemorySpanExporter],
) -> None:
    client, metrics, _ = instrumented_client
    client.get("/items/42")
    deltas = [value for name, value, _ in metrics.calls if name == "http.server.active_requests"]
    assert deltas == [1, -1]


def test_http_duration_and_request_counter_are_recorded(
    instrumented_client: tuple[TestClient, RecordingMetrics, InMemorySpanExporter],
) -> None:
    client, metrics, _ = instrumented_client
    client.get("/items/42")
    names = [name for name, _, _ in metrics.calls]
    assert "http.server.requests" in names
    assert "http.server.duration" in names


def test_http_span_contains_only_template_and_bounded_http_fields(
    instrumented_client: tuple[TestClient, RecordingMetrics, InMemorySpanExporter],
) -> None:
    client, _, exporter = instrumented_client
    client.get("/items/member-secret?token=secret")
    span = exporter.get_finished_spans()[-1]
    assert span.name == "http.request"
    assert span.attributes["http.route"] == "/items/{item_id}"
    assert span.attributes["http.response.status_code"] == 200
    serialized = repr(span.attributes)
    assert "member-secret" not in serialized
    assert "token=secret" not in serialized


def test_traceparent_is_extracted(
    instrumented_client: tuple[TestClient, RecordingMetrics, InMemorySpanExporter],
) -> None:
    client, _, exporter = instrumented_client
    trace_id = "0af7651916cd43dd8448eb211c80319c"
    client.get(
        "/items/42",
        headers={"traceparent": f"00-{trace_id}-b7ad6b7169203331-01"},
    )
    assert f"{exporter.get_finished_spans()[-1].context.trace_id:032x}" == trace_id


def test_contextvars_are_isolated_between_concurrent_tasks() -> None:
    async def worker(request_id: str) -> str:
        with bind_context(request_id=request_id):
            await asyncio.sleep(0)
            return correlation_fields()["request_id"]

    async def run() -> list[str]:
        return list(await asyncio.gather(worker("request-a"), worker("request-b")))

    assert asyncio.run(run()) == ["request-a", "request-b"]
    assert current_context().request_id is None


def test_http_methods_are_bounded() -> None:
    assert _bounded_method("get") == "GET"
    assert _bounded_method("POST") == "POST"
    assert _bounded_method("TRACE") == "OTHER"
