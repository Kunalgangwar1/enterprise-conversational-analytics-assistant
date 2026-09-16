"""Controlled authentication and authorization domain failures."""


class AuthenticationError(RuntimeError):
    """Raised when no trustworthy authenticated principal can be produced."""


class PermissionDeniedError(RuntimeError):
    """Raised when an authenticated principal lacks a required permission."""
