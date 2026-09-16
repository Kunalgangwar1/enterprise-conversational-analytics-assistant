"""Persistence abstraction for typed, atomically mutated session state."""

from collections.abc import Callable
from typing import Protocol

from app.sessions.identity import SessionIdentity
from app.sessions.models import SessionState

SessionMutation = Callable[[SessionState | None], SessionState]


class SessionStore(Protocol):
    """Storage contract consumed by the session service."""

    def load(self, identity: SessionIdentity) -> SessionState | None:
        """Load a state, returning None when it does not yet exist."""

        ...

    def save(self, state: SessionState) -> None:
        """Persist a complete validated state."""

        ...

    def update(
        self,
        identity: SessionIdentity,
        mutation: SessionMutation,
    ) -> SessionState:
        """Atomically apply a state mutation and return the persisted result."""

        ...

    def delete(self, identity: SessionIdentity) -> None:
        """Delete a state if it exists."""

        ...

    def close(self) -> None:
        """Release backend resources."""

        ...
