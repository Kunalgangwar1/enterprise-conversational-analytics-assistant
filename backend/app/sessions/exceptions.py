"""Domain-specific exceptions for session identity and persistence."""


class SessionError(Exception):
    """Base exception for the session subsystem."""


class InvalidTabIdError(SessionError, ValueError):
    """Raised when an X-Tab-Id value is not safe and valid."""


class SessionStoreError(SessionError):
    """Raised when durable session state cannot be read or written safely."""


class SessionCorruptError(SessionStoreError):
    """Raised when persisted state is malformed or uses an unsupported schema."""


class SessionStoreUnavailableError(SessionStoreError):
    """Raised when the configured shared session backend cannot be reached."""


class SessionConflictError(SessionStoreError):
    """Raised when an atomic session update repeatedly loses an optimistic lock."""
