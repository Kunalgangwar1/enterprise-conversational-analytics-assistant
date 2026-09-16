"""Dependency-free objective evaluation metrics and SQL result comparison."""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from datetime import date, datetime
from decimal import Decimal
from typing import Any


def accuracy(correct: int, total: int) -> float:
    return correct / total if total else 0.0


def hit_at_k(actual: Sequence[str], expected: Iterable[str], k: int) -> float:
    return float(bool(set(actual[:k]) & set(expected)))


def recall_at_k(actual: Sequence[str], expected: Iterable[str], k: int) -> float:
    expected_set = set(expected)
    return len(set(actual[:k]) & expected_set) / len(expected_set) if expected_set else 1.0


def reciprocal_rank(actual: Sequence[str], expected: Iterable[str]) -> float:
    expected_set = set(expected)
    return next(
        (1.0 / rank for rank, item in enumerate(actual, start=1) if item in expected_set), 0.0
    )


def mae(actual: Sequence[float], predicted: Sequence[float]) -> float:
    _validate_numeric_pairs(actual, predicted)
    return sum(abs(left - right) for left, right in zip(actual, predicted, strict=True)) / len(
        actual
    )


def rmse(actual: Sequence[float], predicted: Sequence[float]) -> float:
    _validate_numeric_pairs(actual, predicted)
    return math.sqrt(
        sum((left - right) ** 2 for left, right in zip(actual, predicted, strict=True))
        / len(actual)
    )


def smape(actual: Sequence[float], predicted: Sequence[float]) -> float:
    _validate_numeric_pairs(actual, predicted)
    terms = []
    for left, right in zip(actual, predicted, strict=True):
        denominator = abs(left) + abs(right)
        terms.append(0.0 if denominator == 0 else 200 * abs(left - right) / denominator)
    return sum(terms) / len(terms)


def percentile(values: Sequence[float], percentage: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, math.ceil(percentage * len(ordered)) - 1)
    return ordered[index]


def latency_summary(values: Sequence[float]) -> dict[str, float]:
    return {
        "mean": sum(values) / len(values) if values else 0.0,
        "p50": percentile(values, 0.50),
        "p95": percentile(values, 0.95),
        "max": max(values, default=0.0),
    }


def normalize_rows(
    columns: Sequence[str],
    rows: Sequence[dict[str, Any]],
    *,
    order_sensitive: bool,
) -> tuple[tuple[str, ...], tuple[tuple[Any, ...], ...]]:
    normalized_columns = tuple(column.lower() for column in columns)
    normalized_rows = tuple(
        tuple(_normalize_value(row.get(column)) for column in columns) for row in rows
    )
    if not order_sensitive:
        normalized_rows = tuple(sorted(normalized_rows, key=repr))
    return normalized_columns, normalized_rows


def results_equivalent(
    left_columns: Sequence[str],
    left_rows: Sequence[dict[str, Any]],
    right_columns: Sequence[str],
    right_rows: Sequence[dict[str, Any]],
    *,
    order_sensitive: bool = False,
    numeric_tolerance: float = 0.0,
) -> bool:
    left = normalize_rows(left_columns, left_rows, order_sensitive=order_sensitive)
    right = normalize_rows(right_columns, right_rows, order_sensitive=order_sensitive)
    if left[0] != right[0] or len(left[1]) != len(right[1]):
        return False
    return all(_rows_equal(a, b, numeric_tolerance) for a, b in zip(left[1], right[1], strict=True))


def _rows_equal(left: tuple[Any, ...], right: tuple[Any, ...], tolerance: float) -> bool:
    if len(left) != len(right):
        return False
    for first, second in zip(left, right, strict=True):
        if isinstance(first, Decimal) and isinstance(second, Decimal):
            if abs(first - second) > Decimal(str(tolerance)):
                return False
        elif first != second:
            return False
    return True


def _normalize_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool | int):
        return Decimal(int(value))
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value


def _validate_numeric_pairs(actual: Sequence[float], predicted: Sequence[float]) -> None:
    if not actual or len(actual) != len(predicted):
        raise ValueError("Metric inputs must be non-empty and equally sized")
