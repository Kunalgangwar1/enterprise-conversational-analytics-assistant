"""Sanitized query-layer exceptions."""

from enum import StrEnum


class QueryValidationReason(StrEnum):
    """Machine-readable outcomes from the shared read-only SQL guard."""

    BLANK = "blank"
    PARSE_ERROR = "parse_error"
    MULTIPLE_STATEMENTS = "multiple_statements"
    NON_QUERY = "non_query"
    FORBIDDEN_OPERATION = "forbidden_operation"


class QueryError(Exception):
    """Base exception for query validation, configuration, and execution."""


class QueryValidationError(QueryError):
    """Raised when SQL violates the read-only query policy."""

    def __init__(
        self,
        message: str,
        *,
        reason: QueryValidationReason | None = None,
    ) -> None:
        super().__init__(message)
        self.reason = reason


class QueryTimeoutError(QueryError):
    """Raised when PostgreSQL cancels a statement at the configured timeout."""


class QueryExecutionError(QueryError):
    """Raised when the database cannot execute an otherwise valid query."""


class QueryConfigurationError(QueryError):
    """Raised when safe query execution is not configured correctly."""
