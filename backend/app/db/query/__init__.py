"""Safe, database-independent query execution boundary."""

from app.db.query.base import QueryExecutor
from app.db.query.exceptions import (
    QueryConfigurationError,
    QueryDependencyUnavailableError,
    QueryError,
    QueryExecutionError,
    QueryPermissionError,
    QueryPoolTimeoutError,
    QueryTimeoutError,
    QueryValidationError,
    QueryValidationReason,
)
from app.db.query.factory import get_query_executor
from app.db.query.models import QueryExecutionResult

__all__ = [
    "QueryConfigurationError",
    "QueryDependencyUnavailableError",
    "QueryError",
    "QueryExecutionError",
    "QueryPermissionError",
    "QueryPoolTimeoutError",
    "QueryExecutionResult",
    "QueryExecutor",
    "QueryTimeoutError",
    "QueryValidationError",
    "QueryValidationReason",
    "get_query_executor",
]
