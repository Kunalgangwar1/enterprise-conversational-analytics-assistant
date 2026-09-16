"""Unit coverage for versioned Redis session persistence and concurrency."""

import json
from datetime import UTC, datetime
from typing import cast
from uuid import uuid4

import pytest
from redis import Redis

from app.core.chat_modes import ChatModeKey, chat_mode_registry
from app.sessions.exceptions import (
    SessionConflictError,
    SessionCorruptError,
    SessionStoreUnavailableError,
)
from app.sessions.identity import SessionIdentity
from app.sessions.models import SessionState
from app.sessions.redis_store import RedisSessionStore
from app.sessions.service import SessionService
from tests.sessions.fakes import FakeRedisBackend, FakeRedisClient


def _identity(
    *, subject: str = "user-a", tab: str = "tab-a", browser: str | None = None
) -> SessionIdentity:
    return SessionIdentity(
        browser_session_id=browser or str(uuid4()),
        tab_id=tab,
        owner_subject=subject,
    )


def _state(identity: SessionIdentity, *, sql: str | None = "SELECT 1") -> SessionState:
    timestamp = datetime(2026, 1, 1, tzinfo=UTC)
    return SessionState(
        browser_session_id=identity.browser_session_id,
        tab_id=identity.tab_id,
        owner_subject=identity.owner_subject,
        selected_mode=ChatModeKey.SQL,
        last_generated_sql=sql,
        last_token_mapping={"T001": "synthetic"},
        created_at=timestamp,
        updated_at=timestamp,
    )


def _store(
    backend: FakeRedisBackend,
    *,
    retries: int = 3,
    ttl: int = 60,
) -> tuple[RedisSessionStore, FakeRedisClient]:
    client = FakeRedisClient(backend)
    store = RedisSessionStore(
        "redis://unused",
        key_prefix="eca:test",
        ttl_seconds=ttl,
        max_update_retries=retries,
        client=cast(Redis, client),
    )
    return store, client


def test_round_trip_uses_versioned_json_and_no_pickle() -> None:
    backend = FakeRedisBackend()
    store, _ = _store(backend)
    identity = _identity()
    state = _state(identity)

    store.save(state)

    assert store.load(identity) == state
    payload = backend.entries[store.key_for(identity)].value
    document = json.loads(payload)
    assert document["schema_version"] == 1
    assert document["state"]["last_generated_sql"] == "SELECT 1"
    assert not payload.startswith("\x80")


def test_key_contains_only_prefix_and_sha256_digest() -> None:
    backend = FakeRedisBackend()
    store, _ = _store(backend)
    identity = _identity(subject="private-user", tab="private-tab", browser=str(uuid4()))

    key = store.key_for(identity)

    prefix, digest = key.rsplit(":", 1)
    assert prefix == "eca:test"
    assert len(digest) == 64
    assert set(digest) <= set("0123456789abcdef")
    assert identity.owner_subject not in key
    assert identity.browser_session_id not in key
    assert identity.tab_id not in key


def test_save_and_update_set_and_refresh_ttl() -> None:
    backend = FakeRedisBackend()
    store, client = _store(backend, ttl=30)
    identity = _identity()
    store.save(_state(identity))
    assert client.ttl(store.key_for(identity)) == 30

    backend.advance(10)
    updated = store.update(identity, lambda current: cast(SessionState, current))

    assert updated.last_generated_sql == "SELECT 1"
    assert client.ttl(store.key_for(identity)) == 30


def test_expired_state_loads_as_missing() -> None:
    backend = FakeRedisBackend()
    store, _ = _store(backend, ttl=5)
    identity = _identity()
    store.save(_state(identity))

    backend.advance(5)

    assert store.load(identity) is None


@pytest.mark.parametrize(
    "payload",
    ["not-json", '{"schema_version":2,"state":{}}', '{"schema_version":1,"state":{}}'],
)
def test_corrupt_or_unsupported_payload_is_rejected(payload: str) -> None:
    backend = FakeRedisBackend()
    store, client = _store(backend)
    identity = _identity()
    client.set(store.key_for(identity), payload, ex=60)

    with pytest.raises(SessionCorruptError):
        store.load(identity)


def test_identity_mismatch_is_rejected() -> None:
    backend = FakeRedisBackend()
    store, client = _store(backend)
    identity = _identity()
    other = _identity()
    client.set(store.key_for(identity), store._serialize(_state(other)), ex=60)

    with pytest.raises(SessionCorruptError, match="identity"):
        store.load(identity)


def test_watch_conflict_retries_then_succeeds() -> None:
    backend = FakeRedisBackend()
    backend.watch_conflicts_remaining = 1
    store, _ = _store(backend, retries=2)
    identity = _identity()
    calls = 0

    def mutation(current: SessionState | None) -> SessionState:
        nonlocal calls
        calls += 1
        return current or _state(identity)

    assert store.update(identity, mutation) == _state(identity)
    assert calls == 2


def test_exhausted_watch_retries_raise_conflict() -> None:
    backend = FakeRedisBackend()
    backend.watch_conflicts_remaining = 3
    store, _ = _store(backend, retries=3)
    identity = _identity()

    with pytest.raises(SessionConflictError):
        store.update(identity, lambda _current: _state(identity))


@pytest.mark.parametrize("operation", ["load", "save", "update", "delete"])
def test_redis_outage_is_explicit_and_never_falls_back(operation: str) -> None:
    backend = FakeRedisBackend()
    store, _ = _store(backend)
    identity = _identity()
    backend.unavailable = True

    with pytest.raises(SessionStoreUnavailableError):
        if operation == "load":
            store.load(identity)
        elif operation == "save":
            store.save(_state(identity))
        elif operation == "update":
            store.update(identity, lambda _current: _state(identity))
        else:
            store.delete(identity)


def test_two_store_instances_share_state() -> None:
    backend = FakeRedisBackend()
    writer, _ = _store(backend)
    reader, _ = _store(backend)
    identity = _identity()

    writer.save(_state(identity))

    assert reader.load(identity) == _state(identity)


def test_conflict_retry_preserves_other_instances_turn_without_lost_update() -> None:
    backend = FakeRedisBackend()
    first_store, _ = _store(backend)
    second_store, _ = _store(backend)
    first = SessionService(first_store, chat_mode_registry)
    second = SessionService(second_store, chat_mode_registry)
    identity = _identity()
    first.select_mode(identity, "sql")
    backend.watch_conflicts_remaining = 1
    backend.conflict_hook = lambda: second.complete_turn(
        identity,
        user_content="second user",
        assistant_content="second answer",
        last_generated_sql="SELECT 2",
        last_token_mapping=None,
    )

    first.complete_turn(
        identity,
        user_content="first user",
        assistant_content="first answer",
        last_generated_sql="SELECT 1",
        last_token_mapping={"T001": "synthetic"},
    )

    persisted = second_store.load(identity)
    assert persisted is not None
    assert [message.content for message in persisted.chat_history] == [
        "second user",
        "second answer",
        "first user",
        "first answer",
    ]
    assert persisted.last_generated_sql == "SELECT 1"


def test_subject_and_tab_isolation_and_targeted_reset() -> None:
    backend = FakeRedisBackend()
    store, _ = _store(backend)
    service = SessionService(store, chat_mode_registry)
    browser = str(uuid4())
    target = _identity(subject="user-a", tab="tab-a", browser=browser)
    other_tab = _identity(subject="user-a", tab="tab-b", browser=browser)
    other_user = _identity(subject="user-b", tab="tab-a", browser=browser)
    for identity, sql in ((target, "SELECT 1"), (other_tab, "SELECT 2"), (other_user, "SELECT 3")):
        service.complete_turn(
            identity,
            user_content="question",
            assistant_content="answer",
            last_generated_sql=sql,
            last_token_mapping={"T001": identity.owner_subject or "legacy"},
        )

    service.reset(target)

    assert store.load(target).last_generated_sql is None  # type: ignore[union-attr]
    assert store.load(other_tab).last_generated_sql == "SELECT 2"  # type: ignore[union-attr]
    assert store.load(other_user).last_generated_sql == "SELECT 3"  # type: ignore[union-attr]


def test_latest_pending_sql_and_mapping_are_shared_without_history_or_custom_context() -> None:
    backend = FakeRedisBackend()
    writer, _ = _store(backend)
    reader, _ = _store(backend)
    identity = _identity()
    SessionService(writer, chat_mode_registry).complete_turn(
        identity,
        user_content="synthetic question",
        assistant_content="synthetic answer",
        last_generated_sql="SELECT * FROM synthetic WHERE id = 'T001'",
        last_token_mapping={"T001": "synthetic-id"},
    )

    persisted = reader.load(identity)
    assert persisted is not None
    assert persisted.last_generated_sql.endswith("'T001'")
    assert persisted.last_token_mapping == {"T001": "synthetic-id"}
    raw_state = json.loads(backend.entries[reader.key_for(identity)].value)["state"]
    assert "custom_context" not in raw_state
    assert "token_mapping_history" not in raw_state


def test_close_releases_client() -> None:
    backend = FakeRedisBackend()
    store, client = _store(backend)

    store.close()

    assert client.closed is True
    assert backend.closed_clients == 1
