"""Input validation and authenticated abuse-control tests."""

from pathlib import Path
from typing import cast
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel, ValidationError
from redis import Redis
from redis.exceptions import ConnectionError

from app.api.routes.data_discovery import DataDiscoveryQuery
from app.api.routes.data_quality import DataQualityQuery
from app.api.routes.knowledge_catalog import KnowledgeCatalogQuery
from app.api.routes.semantica import SemanticaQuery
from app.chat.models import ChatRequest
from app.core.config import Settings
from app.data_discovery.models import DataDiscoveryResult
from app.data_discovery.search import DataDiscoveryService
from app.main import create_app
from app.security.exceptions import RateLimitUnavailableError
from app.security.rate_limit import (
    InMemoryRateLimiter,
    RateLimitDecision,
    RedisRateLimiter,
)


@pytest.mark.parametrize(
    "model",
    [DataDiscoveryQuery, KnowledgeCatalogQuery, DataQualityQuery, SemanticaQuery],
)
def test_specialist_question_length_is_bounded(model: type[BaseModel]) -> None:
    assert model(question="x" * 4_000).question == "x" * 4_000
    with pytest.raises(ValidationError):
        model(question="x" * 4_001)


def test_chat_message_and_custom_context_limits_are_explicit() -> None:
    request = ChatRequest(message="x" * 4_000, custom_context="y" * 8_000)
    assert len(request.message) == 4_000
    assert len(request.custom_context or "") == 8_000

    with pytest.raises(ValidationError):
        ChatRequest(message="x" * 4_001)
    with pytest.raises(ValidationError):
        ChatRequest(message="ok", custom_context="y" * 8_001)


@pytest.mark.parametrize("invalid", ["bad\x00text", "bad\x08text", "bad\x7ftext"])
def test_problematic_control_characters_are_rejected(invalid: str) -> None:
    with pytest.raises(ValidationError, match="control characters"):
        ChatRequest(message=invalid)
    with pytest.raises(ValidationError, match="control characters"):
        DataDiscoveryQuery(question=invalid)


def test_normal_multiline_text_is_allowed() -> None:
    request = ChatRequest(message="line one\nline two\tvalue", custom_context="context\r\nvalue")
    assert "line two" in request.message


def test_memory_rate_limit_threshold_retry_and_window_reset() -> None:
    now = [1.0]
    limiter = InMemoryRateLimiter(
        requests=2,
        window_seconds=10,
        clock=lambda: now[0],
    )

    assert limiter.check("user-a", "chat").allowed is True
    assert limiter.check("user-a", "chat").allowed is True
    denied = limiter.check("user-a", "chat")
    assert denied.allowed is False
    assert denied.retry_after_seconds == 9

    now[0] = 11.0
    assert limiter.check("user-a", "chat").allowed is True


def test_rate_limit_identity_is_hashed_and_users_and_scopes_are_independent() -> None:
    limiter = InMemoryRateLimiter(requests=1, window_seconds=60, clock=lambda: 1.0)
    subject = "alice@example.invalid"

    key = limiter.key_for(subject, "chat")
    assert len(key) == 64
    assert subject not in key
    assert limiter.check(subject, "chat").allowed is True
    assert limiter.check(subject, "chat").allowed is False
    assert limiter.check("bob@example.invalid", "chat").allowed is True
    assert limiter.check(subject, "execute_sql").allowed is True


class _RedisEvalClient:
    def __init__(self, *, unavailable: bool = False) -> None:
        self.count = 0
        self.unavailable = unavailable
        self.calls: list[tuple[object, ...]] = []
        self.closed = False

    def eval(self, *args: object) -> list[int]:
        if self.unavailable:
            raise ConnectionError("redis://:secret@internal/0")
        self.calls.append(args)
        self.count += 1
        return [self.count, 17]

    def close(self) -> None:
        self.closed = True


def test_redis_rate_limit_is_atomic_hashed_and_bounded() -> None:
    client = _RedisEvalClient()
    limiter = RedisRateLimiter(
        "redis://unused",
        key_prefix="eca:test-rate",
        requests=1,
        window_seconds=30,
        client=cast(Redis, client),
    )

    first = limiter.check("private-subject", "chat")
    second = limiter.check("private-subject", "chat")
    key = limiter.key_for("private-subject", "chat")

    assert first.allowed is True
    assert second == RateLimitDecision(allowed=False, remaining=0, retry_after_seconds=17)
    assert "private-subject" not in key
    assert client.calls[0][1:] == (1, key, 30)


def test_redis_rate_limit_outage_fails_safe_without_details() -> None:
    client = _RedisEvalClient(unavailable=True)
    limiter = RedisRateLimiter(
        "redis://unused",
        key_prefix="eca:test-rate",
        requests=1,
        window_seconds=30,
        client=cast(Redis, client),
    )

    with pytest.raises(RateLimitUnavailableError) as captured:
        limiter.check("user-a", "chat")

    assert "secret" not in str(captured.value)


def test_expensive_endpoint_returns_429_and_retry_after(tmp_path: Path) -> None:
    settings = Settings(
        _env_file=None,
        app_env="test",
        artifacts_output_dir=tmp_path,
        rate_limit_requests=1,
        rate_limit_window_seconds=60,
    )
    service = MagicMock(spec=DataDiscoveryService)
    service.search.return_value = DataDiscoveryResult()
    application = create_app(settings, data_discovery_service=service)

    with TestClient(application) as client:
        first = client.post("/api/data-discovery/query", json={"question": "claims"})
        denied = client.post("/api/data-discovery/query", json={"question": "claims"})

    assert first.status_code == 200
    assert denied.status_code == 429
    assert 1 <= int(denied.headers["retry-after"]) <= 60
    assert denied.json()["error"]["code"] == "rate_limit_exceeded"


class _UnavailableLimiter:
    def check(self, subject: str, scope: str) -> RateLimitDecision:
        del subject, scope
        raise RateLimitUnavailableError("redis://:sentinel-secret@internal/0")

    def close(self) -> None:
        pass


def test_rate_limit_backend_outage_returns_sanitized_503(tmp_path: Path) -> None:
    settings = Settings(_env_file=None, app_env="test", artifacts_output_dir=tmp_path)
    service = MagicMock(spec=DataDiscoveryService)
    application = create_app(
        settings,
        data_discovery_service=service,
        rate_limiter=_UnavailableLimiter(),
    )

    with TestClient(application) as client:
        response = client.post("/api/data-discovery/query", json={"question": "claims"})

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "rate_limit_unavailable"
    assert "sentinel-secret" not in response.text


def test_secure_cookie_attributes_remain_non_authentication_session_metadata(
    tmp_path: Path,
) -> None:
    settings = Settings(
        _env_file=None,
        app_env="test",
        artifacts_output_dir=tmp_path,
        session_cookie_secure=True,
    )
    with TestClient(create_app(settings)) as client:
        response = client.post("/chat/select-mode", json={"mode": "sql"})

    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie
    assert "secure" in cookie
    assert "samesite=lax" in cookie
    assert "path=/" in cookie
    assert "domain=" not in cookie
    assert f"max-age={settings.session_max_age_seconds}" in cookie
