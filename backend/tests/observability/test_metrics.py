from __future__ import annotations

from types import SimpleNamespace

import pytest
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader

from app.api.errors import APIError
from app.observability.metrics import (
    METRIC_CATALOG,
    ApplicationMetrics,
    bounded_attributes,
    route_category,
    set_metrics,
)
from app.security.rate_limit import RateLimitDecision, enforce_rate_limit


def _points(reader: InMemoryMetricReader) -> dict[str, list[object]]:
    result: dict[str, list[object]] = {}
    data = reader.get_metrics_data()
    assert data is not None
    for resource_metrics in data.resource_metrics:
        for scope_metrics in resource_metrics.scope_metrics:
            for metric in scope_metrics.metrics:
                result[metric.name] = list(metric.data.data_points)
    return result


def test_catalog_contains_required_operational_families() -> None:
    prefixes = {name.split(".")[0] for name in METRIC_CATALOG}
    assert prefixes >= {
        "http",
        "routing",
        "llm",
        "sql",
        "retrieval",
        "advanced_reasoning",
        "multihop",
        "forecast",
        "session",
        "auth",
        "security",
    }


def test_catalog_never_documents_sensitive_dimensions() -> None:
    forbidden = {
        "request_id",
        "trace_id",
        "session_id",
        "subject",
        "email",
        "member_id",
        "claim_id",
        "sql",
        "prompt",
        "error_message",
        "chunk_id",
    }
    assert all(spec.dimensions.isdisjoint(forbidden) for spec in METRIC_CATALOG.values())


def test_unknown_and_sensitive_attributes_are_dropped() -> None:
    result = bounded_attributes(
        "http.server.requests",
        {
            "method": "GET",
            "route": "/api/health",
            "status_class": "2xx",
            "request_id": "request-secret",
            "subject": "person-secret",
            "session_id": "session-secret",
        },
    )
    assert result == {"method": "GET", "route": "/api/health", "status_class": "2xx"}


def test_unknown_enum_dimension_values_are_dropped() -> None:
    assert bounded_attributes(
        "auth.authentication_failures",
        {"reason_code": "attacker-controlled", "route_category": "other"},
    ) == {"route_category": "other"}


def test_routing_and_forecast_dimensions_use_finite_sets() -> None:
    assert bounded_attributes("routing.requests", {"route": "attacker_value"}) == {}
    assert (
        bounded_attributes("forecast.model_selected", {"model_selected": "arbitrary_model"}) == {}
    )


def test_unbounded_raw_route_is_dropped() -> None:
    assert bounded_attributes(
        "http.server.requests",
        {"route": "/members/John Doe?token=secret", "method": "GET"},
    ) == {"method": "GET"}


def test_model_label_is_syntax_and_length_bounded() -> None:
    assert (
        bounded_attributes(
            "llm.requests",
            {"provider": "gemini", "model": "safe-model:1.0", "operation": "generate"},
        )["model"]
        == "safe-model:1.0"
    )
    assert "model" not in bounded_attributes(
        "llm.requests", {"model": "unsafe model with spaces", "operation": "generate"}
    )


def test_route_category_is_bounded() -> None:
    assert route_category("/api/health") == "health"
    assert route_category("/chat") == "chat"
    assert route_category("/api/v1/sql/execute") == "sql"
    assert route_category("/api/modes") == "api"
    assert route_category("/anything/private") == "other"


def test_counter_records_with_sanitized_attributes() -> None:
    reader = InMemoryMetricReader()
    provider = MeterProvider(metric_readers=[reader])
    metrics = ApplicationMetrics(provider.get_meter("phase27"))
    metrics.record(
        "http.server.requests",
        1,
        {"method": "GET", "route": "/api/health", "request_id": "secret"},
    )
    point = _points(reader)["http.server.requests"][0]
    assert point.value == 1
    assert dict(point.attributes) == {"method": "GET", "route": "/api/health"}
    provider.shutdown()


def test_histogram_records_seconds() -> None:
    reader = InMemoryMetricReader()
    provider = MeterProvider(metric_readers=[reader])
    metrics = ApplicationMetrics(provider.get_meter("phase27"))
    metrics.record("http.server.duration", 0.125, {"method": "GET", "status_class": "2xx"})
    point = _points(reader)["http.server.duration"][0]
    assert point.count == 1
    assert point.sum == 0.125
    assert METRIC_CATALOG["http.server.duration"].unit == "s"
    provider.shutdown()


def test_up_down_counter_balances() -> None:
    reader = InMemoryMetricReader()
    provider = MeterProvider(metric_readers=[reader])
    metrics = ApplicationMetrics(provider.get_meter("phase27"))
    metrics.record("http.server.active_requests", 1, {"method": "POST"})
    metrics.record("http.server.active_requests", -1, {"method": "POST"})
    assert _points(reader)["http.server.active_requests"][0].value == 0
    provider.shutdown()


def test_rate_limit_metric_is_bounded_and_excludes_subject() -> None:
    class DenyingLimiter:
        def check(self, subject: str, scope: str) -> RateLimitDecision:
            assert subject == "private-subject"
            assert scope == "chat"
            return RateLimitDecision(allowed=False, remaining=0, retry_after_seconds=1)

    class Recorder:
        def __init__(self) -> None:
            self.calls: list[tuple[str, dict[str, object]]] = []

        def record(
            self,
            name: str,
            value: int | float = 1,
            attributes: dict[str, object] | None = None,
        ) -> None:
            del value
            self.calls.append((name, attributes or {}))

    recorder = Recorder()
    set_metrics(recorder)  # type: ignore[arg-type]
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(rate_limiter=DenyingLimiter())),
        url=SimpleNamespace(path="/chat"),
    )
    principal = SimpleNamespace(subject="private-subject")
    with pytest.raises(APIError) as error:
        enforce_rate_limit(request, principal, "chat")  # type: ignore[arg-type]
    assert error.value.status_code == 429
    assert recorder.calls == [
        (
            "security.rate_limited_requests",
            {"reason_code": "limit_exceeded", "route_category": "chat"},
        )
    ]
    assert "private-subject" not in repr(recorder.calls)
