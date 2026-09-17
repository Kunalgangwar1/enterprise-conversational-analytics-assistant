"""Application service for isolated conversation-state mutations."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from time import perf_counter
from typing import TypeVar

from app.core.chat_modes import ChatModeConfig, ChatModeRegistry
from app.observability.metrics import get_metrics
from app.observability.tracing import start_span
from app.sessions.exceptions import SessionConflictError, SessionStoreUnavailableError
from app.sessions.identity import SessionIdentity
from app.sessions.models import ChatMessage, ChatRole, SessionState, utc_now
from app.sessions.store import SessionStore


@dataclass(frozen=True)
class ModeSelection:
    """State and display contract resulting from a mode selection."""

    state: SessionState
    mode: ChatModeConfig


class SessionService:
    """Create, load, select, and reset state independently of storage details."""

    def __init__(
        self,
        store: SessionStore,
        mode_registry: ChatModeRegistry,
        *,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._store = store
        self._mode_registry = mode_registry
        self._clock = clock

    def get_or_create(self, identity: SessionIdentity) -> SessionState:
        """Load current state or create an unpersisted default state."""

        return self._observe(
            "load",
            lambda: self._store.load(identity) or self._new_state(identity),
        )

    def _new_state(self, identity: SessionIdentity) -> SessionState:
        now = self._clock()
        return SessionState(
            browser_session_id=identity.browser_session_id,
            tab_id=identity.tab_id,
            owner_subject=identity.owner_subject,
            created_at=now,
            updated_at=now,
        )

    def select_mode(self, identity: SessionIdentity, requested_mode: str) -> ModeSelection:
        """Validate and persist a canonical selected mode for one tab."""

        mode = self._mode_registry.get(requested_mode)

        def mutate(current: SessionState | None) -> SessionState:
            state = current or self._new_state(identity)
            return state.model_copy(
                update={
                    "selected_mode": mode.key,
                    "updated_at": self._clock(),
                }
            )

        updated = self._observe("select_mode", lambda: self._store.update(identity, mutate))
        return ModeSelection(state=updated, mode=mode)

    def reset(self, identity: SessionIdentity) -> SessionState:
        """Clear conversational fields while preserving identity, mode, and creation time."""

        def mutate(current: SessionState | None) -> SessionState:
            state = current or self._new_state(identity)
            return state.model_copy(
                update={
                    "chat_history": [],
                    "last_generated_sql": None,
                    "last_token_mapping": None,
                    "follow_up_questions": [],
                    "updated_at": self._clock(),
                }
            )

        return self._observe("reset", lambda: self._store.update(identity, mutate))

    def complete_turn(
        self,
        identity: SessionIdentity,
        *,
        user_content: str,
        assistant_content: str,
        last_generated_sql: str | None,
        last_token_mapping: dict[str, str] | None,
        follow_up_questions: list[str] | None = None,
    ) -> SessionState:
        """Atomically persist one user-facing turn and only its latest safe execution state."""

        def mutate(current: SessionState | None) -> SessionState:
            state = current or self._new_state(identity)
            return state.model_copy(
                update={
                    "chat_history": [
                        *state.chat_history,
                        ChatMessage(role=ChatRole.USER, content=user_content),
                        ChatMessage(role=ChatRole.ASSISTANT, content=assistant_content),
                    ],
                    "last_generated_sql": last_generated_sql,
                    "last_token_mapping": last_token_mapping,
                    "follow_up_questions": follow_up_questions or [],
                    "updated_at": self._clock(),
                }
            )

        return self._observe("complete_turn", lambda: self._store.update(identity, mutate))

    def _observe(self, operation: str, action: Callable[[], "_ResultT"]) -> "_ResultT":
        started = perf_counter()
        metrics = get_metrics()
        span_name = "session.load" if operation == "load" else "session.update"
        with start_span(
            span_name,
            {"session.operation": operation},
        ) as span:
            try:
                result = action()
            except SessionConflictError:
                metrics.record("session.conflicts", 1, {"operation": operation})
                metrics.record(
                    "session.operation.duration",
                    perf_counter() - started,
                    {"operation": operation, "outcome": "conflict"},
                )
                raise
            except SessionStoreUnavailableError:
                metrics.record("session.unavailable", 1, {"operation": operation})
                metrics.record(
                    "session.operation.duration",
                    perf_counter() - started,
                    {"operation": operation, "outcome": "unavailable"},
                )
                raise
            metrics.record(
                "session.operation.duration",
                perf_counter() - started,
                {"operation": operation, "outcome": "success"},
            )
            span.set_attribute("outcome", "success")
            return result


_ResultT = TypeVar("_ResultT")
