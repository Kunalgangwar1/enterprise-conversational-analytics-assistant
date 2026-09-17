"""Phase 28 failure-injection tests for internal dependencies and recovery."""

from pathlib import Path
from typing import cast
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from redis import Redis

from app.chat.orchestrator import ChatOrchestrator
from app.core.config import Settings
from app.dashboards.service import DashboardService
from app.data_discovery.models import DataDiscoveryResult
from app.data_discovery.search import DataDiscoveryService
from app.main import create_app
from app.reliability.errors import CircuitOpenError
from app.reliability.readiness import ReadinessProbe, ReadinessService
from app.security.rate_limit import RateLimitDecision, RateLimiter, RedisRateLimiter
from app.sessions.exceptions import SessionStoreUnavailableError
from app.sessions.identity import SessionIdentity
from app.sessions.redis_store import RedisSessionStore
from app.sessions.store import SessionStore
from app.sql_results.service import SQLExecutionService
from tests.sessions.fakes import FakeRedisBackend, FakeRedisClient


def _settings(tmp_path: Path) -> Settings:
    return Settings(_env_file=None, app_env="test", artifacts_output_dir=tmp_path)


class _ClosableStore:
    def __init__(self, *, fail_close: bool = False) -> None:
        self.closed = False
        self.fail_close = fail_close

    def close(self) -> None:
        self.closed = True
        if self.fail_close:
            raise RuntimeError("synthetic close failure")


class _ClosableLimiter:
    def __init__(self) -> None:
        self.closed = False

    def check(self, subject: str, scope: str) -> RateLimitDecision:
        del subject, scope
        return RateLimitDecision(True, 1, 0)

    def close(self) -> None:
        self.closed = True


def test_redis_clients_receive_bounded_transport_and_pool_settings() -> None:
    sentinel = MagicMock(spec=Redis)
    expected = {
        "connect_timeout_seconds": 1.0,
        "socket_timeout_seconds": 2.0,
        "pool_timeout_seconds": 3.0,
        "max_connections": 4,
    }
    with (
        patch("app.sessions.redis_store.create_redis_client", return_value=sentinel) as session,
        patch("app.security.rate_limit.create_redis_client", return_value=sentinel) as limiter,
    ):
        RedisSessionStore(
            "redis://session.invalid/0",
            key_prefix="eca:test",
            ttl_seconds=60,
            max_update_retries=2,
            **expected,
        )
        RedisRateLimiter(
            "redis://rate.invalid/0",
            key_prefix="eca:test-rate",
            requests=2,
            window_seconds=60,
            **expected,
        )

    session.assert_called_once_with("redis://session.invalid/0", **expected)
    limiter.assert_called_once_with("redis://rate.invalid/0", **expected)


def test_database_outage_makes_readiness_safe_503(tmp_path: Path) -> None:
    def unavailable() -> None:
        raise OSError("postgresql://admin:secret@database.internal/private")

    application = create_app(
        _settings(tmp_path),
        readiness_service=ReadinessService([ReadinessProbe("database", unavailable)]),
    )

    with TestClient(application) as client:
        response = client.get("/api/ready")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "service_not_ready"
    assert "secret" not in response.text
    assert "postgresql" not in response.text


def test_required_redis_outage_makes_readiness_safe_503(tmp_path: Path) -> None:
    backend = FakeRedisBackend()
    backend.unavailable = True
    redis_client = FakeRedisClient(backend)
    store = RedisSessionStore(
        "redis://unused",
        key_prefix="eca:test",
        ttl_seconds=60,
        max_update_retries=2,
        client=cast(Redis, redis_client),
    )
    application = create_app(
        _settings(tmp_path),
        session_store=store,
        readiness_service=ReadinessService(
            [ReadinessProbe("redis_session", store.check_readiness)]
        ),
    )

    with TestClient(application) as client:
        response = client.get("/api/ready")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "service_not_ready"
    assert "redis" not in response.text.lower()


def test_redis_client_recovers_after_transient_outage_without_restart() -> None:
    backend = FakeRedisBackend()
    redis_client = FakeRedisClient(backend)
    store = RedisSessionStore(
        "redis://unused",
        key_prefix="eca:test",
        ttl_seconds=60,
        max_update_retries=2,
        client=cast(Redis, redis_client),
    )
    identity = SessionIdentity(
        browser_session_id="75c53de9-2984-4307-bd6d-bafad3307052",
        tab_id="tab-a",
        owner_subject="synthetic-user",
    )

    backend.unavailable = True
    with pytest.raises(SessionStoreUnavailableError):
        store.load(identity)

    backend.unavailable = False
    assert store.load(identity) is None


def test_liveness_does_not_run_dependency_or_provider_checks(tmp_path: Path) -> None:
    readiness = MagicMock(spec=ReadinessService)
    application = create_app(_settings(tmp_path), readiness_service=readiness)

    with patch("app.llm.factory.create_llm_client", side_effect=AssertionError):
        with TestClient(application) as client:
            response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    readiness.is_ready.assert_not_called()


def test_shutdown_closes_internal_provider_and_telemetry_resources(
    tmp_path: Path,
) -> None:
    store = _ClosableStore(fail_close=True)
    limiter = _ClosableLimiter()
    sql_service = MagicMock(spec=SQLExecutionService)
    dashboard_service = MagicMock(spec=DashboardService)
    telemetry = MagicMock()

    with (
        patch("app.main.initialize_observability", return_value=telemetry),
        patch("app.main.close_provider_resources") as close_providers,
        patch(
            "app.main.database_engine.dispose",
            side_effect=RuntimeError("synthetic dispose failure"),
        ) as dispose_database,
    ):
        application = create_app(
            _settings(tmp_path),
            session_store=cast(SessionStore, store),
            rate_limiter=cast(RateLimiter, limiter),
            sql_execution_service=sql_service,
            dashboard_service=dashboard_service,
            readiness_service=ReadinessService([]),
        )
        with TestClient(application):
            pass

    sql_service.close.assert_called_once_with()
    dashboard_service.close.assert_called_once_with()
    assert limiter.closed is True
    assert store.closed is True
    close_providers.assert_called_once_with()
    dispose_database.assert_called_once_with()
    telemetry.shutdown.assert_called_once_with()


def test_deterministic_discovery_survives_unrelated_llm_outage(tmp_path: Path) -> None:
    service = MagicMock(spec=DataDiscoveryService)
    service.search.return_value = DataDiscoveryResult()
    application = create_app(
        _settings(tmp_path),
        data_discovery_service=service,
        readiness_service=ReadinessService([]),
    )

    with patch("app.llm.factory.create_llm_client", side_effect=RuntimeError("LLM unavailable")):
        with TestClient(application) as client:
            response = client.post("/api/data-discovery/query", json={"question": "claims"})

    assert response.status_code == 200
    service.search.assert_called_once_with("claims")


def test_open_provider_circuit_returns_sanitized_503(tmp_path: Path) -> None:
    orchestrator = MagicMock(spec=ChatOrchestrator)
    orchestrator.run.side_effect = CircuitOpenError("secret provider circuit details")
    application = create_app(
        _settings(tmp_path),
        chat_orchestrator=orchestrator,
        readiness_service=ReadinessService([]),
    )

    with TestClient(application) as client:
        response = client.post(
            "/chat",
            headers={"X-Tab-Id": "tab-a"},
            json={"message": "Analyze synthetic data"},
        )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "provider_unavailable"
    assert "secret" not in response.text
