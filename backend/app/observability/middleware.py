"""ASGI request correlation, safe HTTP metrics, and manual server tracing."""

from __future__ import annotations

import logging
import re
from time import perf_counter
from typing import Any
from uuid import uuid4

from opentelemetry import propagate
from opentelemetry.trace import SpanKind, Status, StatusCode
from starlette.datastructures import Headers

from app.observability.context import bind_context
from app.observability.instrumentation import ObservabilityRuntime
from app.observability.metrics import get_metrics
from app.observability.tracing import start_span

logger = logging.getLogger(__name__)
_REQUEST_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_REQUEST_ID_HEADER = b"x-request-id"
_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"}


class ObservabilityMiddleware:
    def __init__(self, app: Any, *, runtime: ObservabilityRuntime) -> None:
        self.app = app
        self.runtime = runtime

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request_id = _resolve_request_id(Headers(scope=scope).get("x-request-id"))
        method = _bounded_method(scope.get("method", ""))
        status_code = 500
        started = perf_counter()
        metrics = get_metrics()
        metrics.record("http.server.active_requests", 1, {"method": method})
        carrier = {
            key.decode("latin-1"): value.decode("latin-1")
            for key, value in scope.get("headers", [])
            if key.lower() in {b"traceparent", b"tracestate"}
        }
        parent_context = propagate.extract(carrier)

        async def send_with_request_id(message: dict[str, Any]) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = int(message["status"])
                headers = [
                    (key, value)
                    for key, value in message.get("headers", [])
                    if key.lower() != _REQUEST_ID_HEADER
                ]
                headers.append((_REQUEST_ID_HEADER, request_id.encode("ascii")))
                message["headers"] = headers
            await send(message)

        with (
            bind_context(request_id=request_id),
            start_span(
                "http.request",
                {"http.request.method": method},
                kind=SpanKind.SERVER,
                context=parent_context,
            ) as span,
        ):
            try:
                await self.app(scope, receive, send_with_request_id)
            except Exception as exc:
                span.set_attribute("error.type", type(exc).__name__[:128])
                span.set_status(Status(StatusCode.ERROR))
                logger.error(
                    "Unhandled request failure",
                    extra={"error_type": type(exc).__name__, "outcome": "error"},
                )
                raise
            finally:
                route = _route_template(scope)
                duration = perf_counter() - started
                status_class = f"{status_code // 100}xx"
                attributes = {"method": method, "route": route, "status_class": status_class}
                metrics.record("http.server.requests", 1, attributes)
                metrics.record("http.server.duration", duration, attributes)
                if status_code >= 400:
                    metrics.record("http.server.errors", 1, attributes)
                metrics.record("http.server.active_requests", -1, {"method": method})
                span.set_attribute("http.route", route)
                span.set_attribute("http.response.status_code", status_code)
                span.set_attribute("outcome", "success" if status_code < 400 else "error")
                logger.info(
                    "HTTP request completed",
                    extra={
                        "route": route,
                        "operation": "http.request",
                        "outcome": "success" if status_code < 400 else "error",
                    },
                )


def _resolve_request_id(candidate: str | None) -> str:
    if candidate is not None and _REQUEST_ID.fullmatch(candidate):
        return candidate
    return uuid4().hex


def _bounded_method(method: str) -> str:
    normalized = method.upper()
    return normalized if normalized in _METHODS else "OTHER"


def _route_template(scope: dict[str, Any]) -> str:
    route = scope.get("route")
    path = getattr(route, "path", None)
    if isinstance(path, str) and 0 < len(path) <= 128:
        return path
    return "unmatched"
