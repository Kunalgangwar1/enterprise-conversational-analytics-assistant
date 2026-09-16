"""Persistence abstraction for typed session state."""

from typing import Protocol

from app.sessions.identity import SessionIdentity
from app.sessions.models import SessionState


class SessionStore(Protocol):
    """Storage contract consumed by the session service."""

    def load(self, identity: SessionIdentity) -> SessionState | None:
        """Load a state, returning None when it does not yet exist."""

        ...

    def save(self, state: SessionState) -> None:
        """Persist a complete validated state."""

        ...

    def delete(self, identity: SessionIdentity) -> None:
        """Delete a state if it exists."""

        ...
