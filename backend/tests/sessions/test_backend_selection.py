"""Configuration, factory, lifecycle, and HTTP contracts for session backends."""

from decimal import Decimal
from pathlib import Path
from typing import cast
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from redis import Redis

from app.core.chat_modes import chat_mode_registry
from app.core.config import Settings
from app.main import create_app
from app.sessions.factory import build_session_store
from app.sessions.identity import SessionIdentity
from app.sessions.json_store import JsonFileSessionStore
from app.sessions.redis_store import RedisSessionStore
from app.sessions.service import SessionService
from app.sql_results import (
    ChartMetadata,
    ChartType,
    SQLAnalyticsResult,
    SQLExecutionService,
    SummarySource,
)
from tests.sessions.fakes import FakeRedisBackend, FakeRedisClient


def _store(
    backend: FakeRedisBackend, *, retries: int = 2
) -> tuple[RedisSessionStore, FakeRedisClient]:
    client = FakeRedisClient(backend)
    return (
        RedisSessionStore(
            "redis://unused",
            key_prefix="eca:test",
            ttl_seconds=60,
            max_update_retries=retries,
            client=cast(Redis, client),
        ),
        client,
    )


def _settings(tmp_path: Path, **overrides: object) -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        artifacts_output_dir=tmp_path,
        **overrides,
    )


def _analytics_result() -> SQLAnalyticsResult:
    return SQLAnalyticsResult(
        columns=["value"],
        rows=[{"value": Decimal("1")}],
        row_count=1,
        truncated=False,
        execution_elapsed_ms=1.0,
        summary="Synthetic result.",
        summary_source=SummarySource.DETERMINISTIC,
        chart=ChartMetadata(
            chart_type=ChartType.TABLE,
            title="Synthetic result",
            selection_rule="table_fallback",
        ),
    )


def test_default_backend_is_json_and_requires_no_redis_url(tmp_path: Path) -> None:
    settings = _settings(tmp_path)

    store = build_session_store(settings)

    assert settings.session_store_backend == "json"
    assert isinstance(store, JsonFileSessionStore)


def test_default_app_startup_does_not_construct_redis(tmp_path: Path) -> None:
    with patch("app.sessions.factory.RedisSessionStore", side_effect=AssertionError):
        application = create_app(_settings(tmp_path))

    assert isinstance(application.state.session_service._store, JsonFileSessionStore)


def test_factory_selects_redis_with_configured_values(tmp_path: Path) -> None:
    settings = _settings(
        tmp_path,
        session_store_backend="redis",
        session_redis_url="redis://:secret@redis.internal:6379/2",
        session_redis_key_prefix="custom:sessions",
        session_max_age_seconds=321,
        session_redis_max_update_retries=7,
    )
    sentinel = MagicMock()
    with patch("app.sessions.factory.RedisSessionStore", return_value=sentinel) as constructor:
        assert build_session_store(settings) is sentinel

    constructor.assert_called_once_with(
        "redis://:secret@redis.internal:6379/2",
        key_prefix="custom:sessions",
        ttl_seconds=321,
        max_update_retries=7,
        connect_timeout_seconds=2.0,
        socket_timeout_seconds=2.0,
        pool_timeout_seconds=2.0,
        max_connections=20,
    )


def test_redis_url_is_required_only_for_redis_backend(tmp_path: Path) -> None:
    assert _settings(tmp_path, session_store_backend="json").session_redis_url is None

    with pytest.raises(ValidationError, match="SESSION_REDIS_URL"):
        _settings(tmp_path, session_store_backend="redis")


def test_unknown_backend_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="session_store_backend"):
        _settings(tmp_path, session_store_backend="memory")


def test_application_lifespan_closes_injected_store(tmp_path: Path) -> None:
    backend = FakeRedisBackend()
    store, client = _store(backend)
    application = create_app(_settings(tmp_path), session_store=store)

    with TestClient(application):
        assert client.closed is False

    assert client.closed is True


@pytest.mark.parametrize(
    ("conflicts", "expected_status", "expected_code"),
    [
        (2, 409, "session_conflict"),
        (0, 503, "session_store_unavailable"),
    ],
)
def test_select_mode_maps_conflict_and_outage_to_safe_http_contracts(
    tmp_path: Path,
    conflicts: int,
    expected_status: int,
    expected_code: str,
) -> None:
    backend = FakeRedisBackend()
    backend.watch_conflicts_remaining = conflicts
    backend.unavailable = expected_status == 503
    store, _ = _store(backend, retries=2)
    settings = _settings(tmp_path)
    application = create_app(settings, session_store=store)

    with TestClient(application) as client:
        response = client.post(
            "/chat/select-mode",
            headers={settings.tab_id_header: "tab-a"},
            json={"mode": "sql"},
        )

    assert response.status_code == expected_status
    assert response.json()["error"]["code"] == expected_code
    assert "redis" not in response.text.lower()
    assert not (tmp_path / "sessions").exists()


def test_second_replica_executes_shared_pending_sql_and_mapping(tmp_path: Path) -> None:
    backend = FakeRedisBackend()
    writer, _ = _store(backend)
    reader, _ = _store(backend)
    browser_id = str(uuid4())
    identity = SessionIdentity(
        browser_session_id=browser_id,
        tab_id="tab-a",
        owner_subject="dev-user",
    )
    SessionService(writer, chat_mode_registry).complete_turn(
        identity,
        user_content="Find synthetic T001",
        assistant_content="Validated.",
        last_generated_sql="SELECT 'T001' AS value",
        last_token_mapping={"T001": "C0000001"},
    )
    execution_service = MagicMock(spec=SQLExecutionService)
    execution_service.execute.return_value = _analytics_result()
    settings = _settings(tmp_path)
    application = create_app(
        settings,
        session_store=reader,
        sql_execution_service=execution_service,
    )

    with TestClient(application) as client:
        client.cookies.set(settings.session_cookie_name, browser_id)
        response = client.post(
            "/chat/execute-sql",
            headers={settings.tab_id_header: "tab-a"},
        )

    assert response.status_code == 200, response.text
    assert execution_service.execute.call_args.kwargs["final_sql"] == "SELECT 'T001' AS value"
    mappings = execution_service.execute.call_args.kwargs["token_mappings"]
    assert mappings[0].token == "T001"
    assert mappings[0].original_value == "C0000001"


def test_other_subject_cannot_execute_shared_pending_sql(tmp_path: Path) -> None:
    backend = FakeRedisBackend()
    writer, _ = _store(backend)
    reader, _ = _store(backend)
    browser_id = str(uuid4())
    owner_identity = SessionIdentity(
        browser_session_id=browser_id,
        tab_id="tab-a",
        owner_subject="user-a",
    )
    SessionService(writer, chat_mode_registry).complete_turn(
        owner_identity,
        user_content="Synthetic question",
        assistant_content="Validated.",
        last_generated_sql="SELECT 1",
        last_token_mapping=None,
    )
    execution_service = MagicMock(spec=SQLExecutionService)
    settings = _settings(tmp_path, auth_dev_subject="user-b")
    application = create_app(
        settings,
        session_store=reader,
        sql_execution_service=execution_service,
    )

    with TestClient(application) as client:
        client.cookies.set(settings.session_cookie_name, browser_id)
        response = client.post(
            "/chat/execute-sql",
            headers={settings.tab_id_header: "tab-a"},
        )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "no_validated_sql"
    execution_service.execute.assert_not_called()
