"""Safe, database-independent query execution boundary."""

from app.db.query.base import QueryExecutor
from app.db.query.exceptions import (
    QueryConfigurationError,
    QueryError,
    QueryExecutionError,
    QueryTimeoutError,
    QueryValidationError,
    QueryValidationReason,
)
from app.db.query.factory import get_query_executor
from app.db.query.models import QueryExecutionResult

__all__ = [
    "QueryConfigurationError",
    "QueryError",
    "QueryExecutionError",
    "QueryExecutionResult",
    "QueryExecutor",
    "QueryTimeoutError",
    "QueryValidationError",
    "QueryValidationReason",
    "get_query_executor",
]
