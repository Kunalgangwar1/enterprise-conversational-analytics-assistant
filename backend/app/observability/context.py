"""Request-safe correlation context shared by logs and telemetry."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

from opentelemetry import trace


@dataclass(frozen=True)
class ObservabilityContext:
    request_id: str | None = None
    route: str | None = None
    operation: str | None = None


_context: ContextVar[ObservabilityContext | None] = ContextVar(
    "observability_context", default=None
)


@contextmanager
def bind_context(
    *,
    request_id: str | None = None,
    route: str | None = None,
    operation: str | None = None,
) -> Iterator[None]:
    """Bind safe correlation fields for the current async/thread context."""

    current = _context.get() or ObservabilityContext()
    token = _context.set(
        ObservabilityContext(
            request_id=request_id if request_id is not None else current.request_id,
            route=route if route is not None else current.route,
            operation=operation if operation is not None else current.operation,
        )
    )
    try:
        yield
    finally:
        _context.reset(token)


def current_context() -> ObservabilityContext:
    return _context.get() or ObservabilityContext()


def correlation_fields() -> dict[str, str]:
    """Return non-empty request and active-span identifiers for structured logs."""

    context = current_context()
    fields = {
        key: value
        for key, value in {
            "request_id": context.request_id,
            "route": context.route,
            "operation": context.operation,
        }.items()
        if value
    }
    span_context = trace.get_current_span().get_span_context()
    if span_context.is_valid:
        fields["trace_id"] = f"{span_context.trace_id:032x}"
        fields["span_id"] = f"{span_context.span_id:016x}"
    return fields
