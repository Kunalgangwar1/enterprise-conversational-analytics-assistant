"""Shared Redis implementation of versioned, atomic session persistence."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError
from redis import Redis
from redis.exceptions import RedisError, WatchError

from app.reliability.redis import create_redis_client
from app.sessions.exceptions import (
    SessionConflictError,
    SessionCorruptError,
    SessionStoreUnavailableError,
)
from app.sessions.identity import SessionIdentity, derive_session_storage_key
from app.sessions.models import SessionState
from app.sessions.store import SessionMutation


class SessionStorageEnvelope(BaseModel):
    """Versioned JSON envelope stored in Redis; pickle is deliberately unsupported."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    state: SessionState


class RedisSessionStore:
    """Persist shared session state with TTL and optimistic Redis transactions."""

    def __init__(
        self,
        redis_url: str,
        *,
        key_prefix: str,
        ttl_seconds: int,
        max_update_retries: int,
        connect_timeout_seconds: float = 2.0,
        socket_timeout_seconds: float = 2.0,
        pool_timeout_seconds: float = 2.0,
        max_connections: int = 20,
        client: Redis | None = None,
    ) -> None:
        self._client = client or create_redis_client(
            redis_url,
            connect_timeout_seconds=connect_timeout_seconds,
            socket_timeout_seconds=socket_timeout_seconds,
            pool_timeout_seconds=pool_timeout_seconds,
            max_connections=max_connections,
        )
        self._key_prefix = key_prefix.rstrip(":")
        self._ttl_seconds = ttl_seconds
        self._max_update_retries = max_update_retries

    def load(self, identity: SessionIdentity) -> SessionState | None:
        """Load and validate one versioned JSON document."""

        try:
            payload = self._client.get(self.key_for(identity))
        except RedisError as exc:
            raise SessionStoreUnavailableError("Redis session storage is unavailable") from exc
        if payload is None:
            return None
        state = self._deserialize(payload)
        self._validate_identity(identity, state)
        return state

    def save(self, state: SessionState) -> None:
        """Persist complete state and establish or refresh its expiry."""

        identity = SessionIdentity(
            browser_session_id=state.browser_session_id,
            tab_id=state.tab_id,
            owner_subject=state.owner_subject,
        )
        try:
            self._client.set(
                self.key_for(identity),
                self._serialize(state),
                ex=self._ttl_seconds,
            )
        except RedisError as exc:
            raise SessionStoreUnavailableError("Redis session storage is unavailable") from exc

    def update(
        self,
        identity: SessionIdentity,
        mutation: SessionMutation,
    ) -> SessionState:
        """Atomically apply a mutation using bounded WATCH/MULTI/EXEC retries."""

        key = self.key_for(identity)
        for _attempt in range(self._max_update_retries):
            try:
                with self._client.pipeline() as pipeline:
                    pipeline.watch(key)
                    payload = pipeline.get(key)
                    current = None if payload is None else self._deserialize(payload)
                    if current is not None:
                        self._validate_identity(identity, current)
                    updated = mutation(current)
                    self._validate_identity(identity, updated)
                    serialized = self._serialize(updated)
                    pipeline.multi()
                    pipeline.set(key, serialized, ex=self._ttl_seconds)
                    pipeline.execute()
                    return updated
            except WatchError:
                continue
            except RedisError as exc:
                raise SessionStoreUnavailableError("Redis session storage is unavailable") from exc
        raise SessionConflictError("session update conflicted too many times")

    def delete(self, identity: SessionIdentity) -> None:
        """Delete one session without affecting other subjects, browsers, or tabs."""

        try:
            self._client.delete(self.key_for(identity))
        except RedisError as exc:
            raise SessionStoreUnavailableError("Redis session storage is unavailable") from exc

    def close(self) -> None:
        """Close the Redis client and its owned connection pool."""

        self._client.close()

    def check_readiness(self) -> None:
        """Raise when the configured shared Redis backend is unavailable."""

        try:
            self._client.ping()
        except RedisError as exc:
            raise SessionStoreUnavailableError("Redis session storage is unavailable") from exc

    def key_for(self, identity: SessionIdentity) -> str:
        """Return a prefix plus the existing SHA-256 identity digest."""

        digest = derive_session_storage_key(
            identity.browser_session_id,
            identity.tab_id,
            identity.owner_subject,
        )
        return f"{self._key_prefix}:{digest}"

    @staticmethod
    def _serialize(state: SessionState) -> str:
        return SessionStorageEnvelope(state=state).model_dump_json()

    @staticmethod
    def _deserialize(payload: str | bytes) -> SessionState:
        try:
            return SessionStorageEnvelope.model_validate_json(payload).state
        except (ValidationError, ValueError, TypeError) as exc:
            raise SessionCorruptError("persisted Redis session state is corrupted") from exc

    @staticmethod
    def _validate_identity(identity: SessionIdentity, state: SessionState) -> None:
        if (
            state.browser_session_id != identity.browser_session_id
            or state.tab_id != identity.tab_id
            or state.owner_subject != identity.owner_subject
        ):
            raise SessionCorruptError("persisted session identity does not match its Redis key")
