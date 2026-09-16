"""Domain-specific exceptions for session identity and persistence."""


class SessionError(Exception):
    """Base exception for the session subsystem."""


class InvalidTabIdError(SessionError, ValueError):
    """Raised when an X-Tab-Id value is not safe and valid."""


class SessionStoreError(SessionError):
    """Raised when durable session state cannot be read or written safely."""
