from datetime import date, datetime
from decimal import Decimal

import pytest

from app.evaluation.metrics import (
    hit_at_k,
    latency_summary,
    mae,
    recall_at_k,
    reciprocal_rank,
    results_equivalent,
    rmse,
    smape,
)


def test_retrieval_metrics_use_known_ranks() -> None:
    actual = ["x", "target", "other"]

    assert hit_at_k(actual, ["target"], 2) == 1
    assert recall_at_k(actual, ["target", "other"], 2) == 0.5
    assert reciprocal_rank(actual, ["target"]) == 0.5


def test_forecast_metrics_are_hand_calculable() -> None:
    actual = [1.0, 3.0]
    predicted = [2.0, 5.0]

    assert mae(actual, predicted) == 1.5
    assert rmse(actual, predicted) == pytest.approx((2.5) ** 0.5)
    assert smape([0.0, 2.0], [0.0, 2.0]) == 0


def test_result_normalization_handles_types_and_unordered_rows() -> None:
    left = [
        {"period": date(2024, 1, 1), "value": Decimal("2.00")},
        {"period": datetime(2024, 2, 1), "value": 3},
    ]
    right = [
        {"period": "2024-02-01T00:00:00", "value": 3.0},
        {"period": "2024-01-01", "value": 2},
    ]

    assert results_equivalent(
        ["period", "value"], left, ["period", "value"], right, order_sensitive=False
    )


def test_result_normalization_detects_wrong_executable_result() -> None:
    assert not results_equivalent(
        ["count"], [{"count": 4}], ["count"], [{"count": 5}], order_sensitive=False
    )


def test_latency_percentiles_are_deterministic_nearest_rank() -> None:
    assert latency_summary([1, 2, 3, 4])["p50"] == 2
    assert latency_summary([1, 2, 3, 4])["p95"] == 4
