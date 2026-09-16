"""Sanitized failures for SQL analytics result processing."""


class SQLResultsError(Exception):
    """Base exception for Phase 13 application services."""


class SQLNotValidatedError(SQLResultsError):
    """Raised when SQL has not reached the Phase 12 ACCEPT state."""


class SQLTokenResolutionError(SQLResultsError):
    """Raised when executable SQL contains an unresolved privacy token."""
