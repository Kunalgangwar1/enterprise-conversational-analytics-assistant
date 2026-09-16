"""Application service for isolated conversation-state mutations."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from threading import RLock

from app.core.chat_modes import ChatModeConfig, ChatModeRegistry
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
        self._lock = RLock()

    def get_or_create(self, identity: SessionIdentity) -> SessionState:
        """Load current state or create an unpersisted default state."""

        state = self._store.load(identity)
        if state is not None:
            return state
        now = self._clock()
        return SessionState(
            browser_session_id=identity.browser_session_id,
            tab_id=identity.tab_id,
            created_at=now,
            updated_at=now,
        )

    def select_mode(self, identity: SessionIdentity, requested_mode: str) -> ModeSelection:
        """Validate and persist a canonical selected mode for one tab."""

        mode = self._mode_registry.get(requested_mode)
        with self._lock:
            current = self.get_or_create(identity)
            updated = current.model_copy(
                update={
                    "selected_mode": mode.key,
                    "updated_at": self._clock(),
                }
            )
            self._store.save(updated)
        return ModeSelection(state=updated, mode=mode)

    def reset(self, identity: SessionIdentity) -> SessionState:
        """Clear conversational fields while preserving identity, mode, and creation time."""

        with self._lock:
            current = self.get_or_create(identity)
            reset_state = current.model_copy(
                update={
                    "chat_history": [],
                    "last_generated_sql": None,
                    "last_token_mapping": None,
                    "follow_up_questions": [],
                    "updated_at": self._clock(),
                }
            )
            self._store.save(reset_state)
        return reset_state

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

        with self._lock:
            current = self.get_or_create(identity)
            updated = current.model_copy(
                update={
                    "chat_history": [
                        *current.chat_history,
                        ChatMessage(role=ChatRole.USER, content=user_content),
                        ChatMessage(role=ChatRole.ASSISTANT, content=assistant_content),
                    ],
                    "last_generated_sql": last_generated_sql,
                    "last_token_mapping": last_token_mapping,
                    "follow_up_questions": follow_up_questions or [],
                    "updated_at": self._clock(),
                }
            )
            self._store.save(updated)
        return updated
