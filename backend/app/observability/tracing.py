"""Safe manual tracing helpers with an explicit attribute allowlist."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from typing import Any

from opentelemetry import trace
from opentelemetry.context import Context
from opentelemetry.trace import Span, SpanKind, Status, StatusCode, Tracer

_ALLOWED_ATTRIBUTES = {
    "http.request.method",
    "http.route",
    "http.response.status_code",
    "service.name",
    "deployment.environment",
    "operation.name",
    "outcome",
    "error.type",
    "selected_mode",
    "resolved_route",
    "strategy",
    "result_type",
    "authorization_outcome",
    "gen_ai.provider.name",
    "gen_ai.request.model",
    "retry_count",
    "db.system",
    "db.operation.name",
    "db.response.returned_rows",
    "db.query.truncated",
    "db.query.timeout_ms",
    "retriever_type",
    "retrieval.result_count",
    "forecast.model_selected",
    "session.operation",
}


def safe_span_attributes(attributes: Mapping[str, object] | None) -> dict[str, Any]:
    """Keep only documented low-cardinality span fields and bounded scalar values."""

    result: dict[str, Any] = {}
    for key, value in (attributes or {}).items():
        if key not in _ALLOWED_ATTRIBUTES or value is None:
            continue
        if isinstance(value, (bool, int, float)):
            result[key] = value
        elif isinstance(value, str) and 0 < len(value) <= 128:
            result[key] = value
    return result


_tracer: Tracer | None = None


def set_tracer(tracer: Tracer | None) -> None:
    global _tracer
    _tracer = tracer


@contextmanager
def start_span(
    name: str,
    attributes: Mapping[str, object] | None = None,
    *,
    kind: SpanKind = SpanKind.INTERNAL,
    context: Context | None = None,
) -> Iterator[Span]:
    """Start a manual span or a harmless non-recording span when tracing is disabled."""

    tracer = _tracer or trace.get_tracer("app.observability.disabled")
    with tracer.start_as_current_span(
        name,
        context=context,
        kind=kind,
        attributes=safe_span_attributes(attributes),
        record_exception=False,
        set_status_on_exception=False,
    ) as span:
        try:
            yield span
        except Exception as exc:
            span.set_attribute("error.type", type(exc).__name__[:128])
            span.set_attribute("outcome", "error")
            span.set_status(Status(StatusCode.ERROR))
            raise
