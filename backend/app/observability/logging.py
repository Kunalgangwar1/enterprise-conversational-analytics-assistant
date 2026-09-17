"""Structured logging with allowlisted fields and centralized redaction."""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime
from typing import Any

from app.observability.context import correlation_fields

_BEARER = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+")
_JWT = re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b")
_DSN = re.compile(r"(?i)\b(postgres(?:ql)?(?:\+[a-z0-9_]+)?|rediss?)://[^\s'\"]+")
_ASSIGNMENT = re.compile(
    r"(?i)\b((?:[a-z0-9]+[_-])*(?:api[_-]?key|password|passwd|secret|access[_-]?key|"
    r"access[_-]?token|refresh[_-]?token|authorization|cookie))\s*[:=]\s*([^\s,;]+)"
)
_EXTRA_FIELDS = {
    "request_id",
    "trace_id",
    "span_id",
    "route",
    "operation",
    "outcome",
    "error_code",
    "error_type",
    "provider",
    "model",
}


def redact(value: object) -> str:
    """Return a log-only redacted representation without mutating application data."""

    text = str(value)
    text = _BEARER.sub("Bearer [REDACTED]", text)
    text = _JWT.sub("[REDACTED_JWT]", text)
    text = _DSN.sub(lambda match: f"{match.group(1)}://[REDACTED]", text)
    return _ASSIGNMENT.sub(lambda match: f"{match.group(1)}=[REDACTED]", text)


class JsonLogFormatter(logging.Formatter):
    """Emit a compact stable JSON schema suitable for stdout collection."""

    def __init__(self, *, service: str, service_version: str, environment: str) -> None:
        super().__init__()
        self._base = {
            "service": service,
            "service_version": service_version,
            "environment": environment,
        }

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": redact(record.getMessage()),
            **self._base,
            **correlation_fields(),
        }
        for field in _EXTRA_FIELDS:
            value = getattr(record, field, None)
            if value is not None and field not in payload:
                payload[field] = redact(value)
        return json.dumps(payload, separators=(",", ":"), sort_keys=True)


class RedactingConsoleFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return redact(super().format(record))


def configure_logging(
    *,
    level: str,
    log_format: str,
    service: str,
    service_version: str,
    environment: str,
) -> None:
    """Configure stdout logging when observability or JSON logging is requested."""

    handler = logging.StreamHandler()
    if log_format == "json":
        formatter: logging.Formatter = JsonLogFormatter(
            service=service,
            service_version=service_version,
            environment=environment,
        )
    else:
        formatter = RedactingConsoleFormatter("%(levelname)s %(name)s %(message)s")
    handler.setFormatter(formatter)
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())
