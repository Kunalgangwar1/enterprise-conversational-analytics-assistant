"""Structured internal query execution results."""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class QueryExecutionResult:
    """A bounded query result without database-driver objects."""

    columns: list[str]
    rows: list[dict[str, Any]]
    row_count: int
    truncated: bool
    elapsed_ms: float
