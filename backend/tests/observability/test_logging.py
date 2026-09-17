from __future__ import annotations

import json
import logging
from asyncio import run

import pytest
from opentelemetry.sdk.trace import TracerProvider

from app.api.errors import APIError, api_error_handler
from app.observability.context import bind_context
from app.observability.logging import JsonLogFormatter, RedactingConsoleFormatter, redact


def _json_message(message: str, **extra: object) -> dict[str, object]:
    record = logging.LogRecord("phase27", logging.INFO, __file__, 1, message, (), None)
    for key, value in extra.items():
        setattr(record, key, value)
    return json.loads(
        JsonLogFormatter(service="backend", service_version="27", environment="test").format(record)
    )


def test_json_log_has_stable_required_fields() -> None:
    payload = _json_message("ready")
    assert (
        payload.items()
        >= {
            "level": "INFO",
            "logger": "phase27",
            "message": "ready",
            "service": "backend",
            "service_version": "27",
            "environment": "test",
        }.items()
    )
    assert payload["timestamp"].endswith("+00:00")


def test_json_log_omits_unset_optional_fields() -> None:
    payload = _json_message("ready")
    assert {"request_id", "trace_id", "span_id", "route", "operation", "outcome"}.isdisjoint(
        payload
    )


def test_json_log_includes_context_and_allowlisted_extras() -> None:
    with bind_context(request_id="req-safe", route="/api/health", operation="probe"):
        payload = _json_message("ready", outcome="success")
    assert (
        payload.items()
        >= {
            "request_id": "req-safe",
            "route": "/api/health",
            "operation": "probe",
            "outcome": "success",
        }.items()
    )


@pytest.mark.parametrize(
    ("unsafe", "fragment"),
    [
        ("Authorization: Bearer abc.DEF_123-xyz", "Authorization=[REDACTED]"),
        ("token eyJhbGciOiJub25l.eyJzdWIiOiIxIn0.signature", "[REDACTED_JWT]"),
        ("postgresql://alice:secret@db.internal/app", "postgresql://[REDACTED]"),
        ("postgresql+psycopg://alice:secret@db/app", "postgresql+psycopg://[REDACTED]"),
        ("redis://:secret@cache:6379/0", "redis://[REDACTED]"),
        ("rediss://user:secret@cache:6379/0", "rediss://[REDACTED]"),
        (
            "GEMINI_API_KEY=gemini-secret AZURE_OPENAI_API_KEY=azure-secret",
            "GEMINI_API_KEY=[REDACTED]",
        ),
        ("password: hunter2", "password=[REDACTED]"),
        ("access_token=abc123", "access_token=[REDACTED]"),
        ("cookie=session-secret", "cookie=[REDACTED]"),
    ],
)
def test_redaction_patterns(unsafe: str, fragment: str) -> None:
    result = redact(unsafe)
    assert fragment in result
    assert "super-secret" not in result
    assert "gemini-secret" not in result
    assert "azure-secret" not in result
    assert "hunter2" not in result
    assert "abc123" not in result
    assert "session-secret" not in result


def test_json_formatter_redacts_message_and_extra_fields() -> None:
    payload = _json_message(
        "failed password=private-value",
        error_type="Bearer secret-token",
    )
    serialized = json.dumps(payload)
    assert "private-value" not in serialized
    assert "secret-token" not in serialized


def test_json_formatter_drops_non_allowlisted_sensitive_extras() -> None:
    payload = _json_message(
        "safe",
        prompt="member 123 diagnosis",
        custom_context="private context",
        sql="SELECT * FROM members",
        token_mapping={"TOKEN": "identity"},
        session_id="session-secret",
    )
    serialized = json.dumps(payload)
    for value in ("member 123", "private context", "SELECT", "identity", "session-secret"):
        assert value not in serialized


def test_console_formatter_also_redacts() -> None:
    formatter = RedactingConsoleFormatter("%(message)s")
    record = logging.LogRecord(
        "phase27", logging.ERROR, __file__, 1, "Bearer do-not-print", (), None
    )
    assert formatter.format(record) == "Bearer [REDACTED]"


def test_active_trace_and_span_ids_are_injected_into_json_logs() -> None:
    provider = TracerProvider()
    with provider.get_tracer("phase27-tests").start_as_current_span("operation"):
        payload = _json_message("correlated")
    assert len(payload["trace_id"]) == 32
    assert len(payload["span_id"]) == 16
    provider.shutdown()


def test_controlled_error_log_does_not_emit_user_facing_message(
    caplog: pytest.LogCaptureFixture,
) -> None:
    error = APIError(
        status_code=400,
        code="safe_error_code",
        message="member private detail should not be logged",
    )
    with caplog.at_level(logging.INFO):
        response = run(api_error_handler(None, error))  # type: ignore[arg-type]
    assert response.status_code == 400
    assert "Controlled API error" in caplog.text
    assert "member private detail" not in caplog.text
