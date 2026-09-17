"""Bounded-cardinality application metric catalog and recording façade."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal

from opentelemetry.metrics import Counter, Histogram, Meter, UpDownCounter

InstrumentKind = Literal["counter", "histogram", "up_down_counter"]


@dataclass(frozen=True)
class MetricSpec:
    kind: InstrumentKind
    unit: str
    description: str
    dimensions: frozenset[str] = frozenset()


def _spec(kind: InstrumentKind, unit: str, description: str, *dimensions: str) -> MetricSpec:
    return MetricSpec(kind, unit, description, frozenset(dimensions))


_CATALOG = {
    "http.server.requests": _spec(
        "counter", "{request}", "Completed HTTP requests", "method", "route", "status_class"
    ),
    "http.server.errors": _spec(
        "counter", "{request}", "HTTP error responses", "method", "route", "status_class"
    ),
    "http.server.duration": _spec(
        "histogram", "s", "HTTP request duration", "method", "route", "status_class"
    ),
    "http.server.active_requests": _spec(
        "up_down_counter", "{request}", "In-flight HTTP requests", "method"
    ),
    "routing.requests": _spec(
        "counter", "{request}", "Routing decisions", "route", "selection_source"
    ),
    "routing.fallbacks": _spec("counter", "{request}", "Fallback routing decisions", "route"),
    "llm.requests": _spec(
        "counter", "{request}", "LLM calls", "provider", "model", "operation", "outcome"
    ),
    "llm.errors": _spec(
        "counter", "{request}", "LLM call failures", "provider", "model", "operation", "outcome"
    ),
    "llm.duration": _spec(
        "histogram", "s", "LLM call duration", "provider", "model", "operation", "outcome"
    ),
    "llm.tokens.input": _spec(
        "counter", "{token}", "Provider-reported input tokens", "provider", "model", "operation"
    ),
    "llm.tokens.output": _spec(
        "counter", "{token}", "Provider-reported output tokens", "provider", "model", "operation"
    ),
    "sql.generation.duration": _spec("histogram", "s", "SQL generation duration", "outcome"),
    "sql.validation.decision": _spec(
        "counter", "{decision}", "SQL validation decisions", "validation_decision"
    ),
    "sql.validation.rewrites": _spec("counter", "{rewrite}", "SQL validation rewrites", "outcome"),
    "sql.execution.duration": _spec("histogram", "s", "Read-only SQL duration", "outcome"),
    "sql.execution.rows": _spec("histogram", "{row}", "Rows returned by read-only SQL", "outcome"),
    "sql.execution.truncated": _spec("counter", "{query}", "Truncated SQL results", "outcome"),
    "sql.execution.errors": _spec("counter", "{query}", "Read-only SQL failures", "outcome"),
    "retrieval.requests": _spec(
        "counter", "{request}", "Retrieval operations", "retriever_type", "outcome"
    ),
    "retrieval.duration": _spec(
        "histogram", "s", "Retrieval duration", "retriever_type", "outcome"
    ),
    "retrieval.result_count": _spec(
        "histogram", "{result}", "Retrieved result count", "retriever_type"
    ),
    "retrieval.no_evidence": _spec(
        "counter", "{request}", "Retrievals with no evidence", "retriever_type"
    ),
    "advanced_reasoning.requests": _spec(
        "counter", "{request}", "Advanced reasoning runs", "outcome"
    ),
    "advanced_reasoning.tool_calls": _spec("counter", "{call}", "Bounded tool calls", "outcome"),
    "advanced_reasoning.replans": _spec(
        "counter", "{replan}", "Advanced reasoning replans", "outcome"
    ),
    "advanced_reasoning.budget_violations": _spec(
        "counter", "{violation}", "Reasoning budget violations", "outcome"
    ),
    "multihop.requests": _spec("counter", "{request}", "Multi-hop SQL runs", "outcome"),
    "multihop.hops": _spec("histogram", "{hop}", "Multi-hop count", "outcome"),
    "multihop.failures": _spec("counter", "{request}", "Multi-hop failures", "outcome"),
    "forecast.requests": _spec("counter", "{request}", "Forecast operations", "outcome"),
    "forecast.duration": _spec("histogram", "s", "Forecast duration", "outcome"),
    "forecast.model_selected": _spec(
        "counter", "{selection}", "Selected forecast model", "model_selected"
    ),
    "forecast.errors": _spec("counter", "{request}", "Forecast failures", "outcome"),
    "session.conflicts": _spec("counter", "{conflict}", "Session update conflicts", "operation"),
    "session.unavailable": _spec(
        "counter", "{failure}", "Session store unavailability", "operation"
    ),
    "session.operation.duration": _spec(
        "histogram", "s", "Session operation duration", "operation", "outcome"
    ),
    "auth.authentication_failures": _spec(
        "counter", "{failure}", "Authentication failures", "reason_code", "route_category"
    ),
    "auth.authorization_denials": _spec(
        "counter", "{denial}", "Authorization denials", "reason_code", "route_category"
    ),
    "security.rate_limited_requests": _spec(
        "counter", "{request}", "Rate-limited requests", "reason_code", "route_category"
    ),
    "security.request_too_large": _spec(
        "counter", "{request}", "Oversized request rejections", "reason_code", "route_category"
    ),
}

METRIC_CATALOG: Mapping[str, MetricSpec] = MappingProxyType(_CATALOG)

_BOUNDED_VALUES: dict[str, frozenset[str]] = {
    "method": frozenset({"GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD", "OTHER"}),
    "status_class": frozenset({"1xx", "2xx", "3xx", "4xx", "5xx"}),
    "outcome": frozenset(
        {"success", "error", "denied", "timeout", "unavailable", "conflict", "truncated"}
    ),
    "selection_source": frozenset({"forced_mode", "heuristic", "llm", "fallback"}),
    "operation": frozenset(
        {
            "generate",
            "generate_structured",
            "load",
            "update",
            "select_mode",
            "reset",
            "complete_turn",
        }
    ),
    "reason_code": frozenset(
        {
            "invalid_token",
            "missing_token",
            "permission_denied",
            "limit_exceeded",
            "storage_unavailable",
            "body_too_large",
            "controlled_error",
            "unexpected_error",
        }
    ),
    "route_category": frozenset({"api", "chat", "sql", "health", "other"}),
    "validation_decision": frozenset({"accept", "reject", "rewrite"}),
    "retriever_type": frozenset(
        {"knowledge_catalog", "data_discovery", "data_quality", "semantica"}
    ),
    "provider": frozenset({"gemini", "azure_openai", "unknown"}),
    "model_selected": frozenset({"naive", "moving_average", "linear_trend", "seasonal_naive"}),
}
_ROUTING_VALUES = frozenset(
    {
        "group_access",
        "sql",
        "forecasting",
        "chat",
        "help",
        "data_discovery",
        "knowledge_catalog",
        "semantica",
        "data_quality",
    }
)


def bounded_attributes(metric_name: str, attributes: Mapping[str, object] | None) -> dict[str, str]:
    """Drop undocumented, high-cardinality, or malformed metric dimensions."""

    spec = METRIC_CATALOG[metric_name]
    result: dict[str, str] = {}
    for key, raw_value in (attributes or {}).items():
        if key not in spec.dimensions:
            continue
        value = str(raw_value).strip()
        if not value or len(value) > 128:
            continue
        allowed = _BOUNDED_VALUES.get(key)
        if allowed is not None and value not in allowed:
            continue
        if key == "route" and metric_name.startswith("routing.") and value not in _ROUTING_VALUES:
            continue
        if key == "route" and not _safe_route(value):
            continue
        if key in {"model", "model_selected"} and not _safe_label(value):
            continue
        result[key] = value
    return result


def _safe_route(value: str) -> bool:
    return len(value) <= 128 and all(
        character.isalnum() or character in "/_{}.*:-" for character in value
    )


def _safe_label(value: str) -> bool:
    return len(value) <= 64 and all(
        character.isalnum() or character in "._:-" for character in value
    )


def route_category(path: str) -> str:
    """Collapse a request path into a small fixed monitoring category."""

    if path == "/api/health" or path == "/api/ready":
        return "health"
    if path.startswith("/chat"):
        return "chat"
    if "sql" in path:
        return "sql"
    if path.startswith("/api/"):
        return "api"
    return "other"


class ApplicationMetrics:
    """Pre-created instruments that become no-ops when metrics are disabled."""

    def __init__(self, meter: Meter | None) -> None:
        self._instruments: dict[str, Counter | Histogram | UpDownCounter] = {}
        if meter is None:
            return
        for name, spec in METRIC_CATALOG.items():
            creator = {
                "counter": meter.create_counter,
                "histogram": meter.create_histogram,
                "up_down_counter": meter.create_up_down_counter,
            }[spec.kind]
            self._instruments[name] = creator(name, unit=spec.unit, description=spec.description)

    def record(
        self,
        name: str,
        value: int | float = 1,
        attributes: Mapping[str, object] | None = None,
    ) -> None:
        instrument = self._instruments.get(name)
        if instrument is None:
            return
        safe_attributes = bounded_attributes(name, attributes)
        if METRIC_CATALOG[name].kind == "histogram":
            instrument.record(value, safe_attributes)  # type: ignore[union-attr]
        else:
            instrument.add(value, safe_attributes)  # type: ignore[union-attr]


_metrics = ApplicationMetrics(None)


def get_metrics() -> ApplicationMetrics:
    return _metrics


def set_metrics(metrics: ApplicationMetrics) -> None:
    global _metrics
    _metrics = metrics
