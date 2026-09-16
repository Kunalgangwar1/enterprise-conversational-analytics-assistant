"""Explicit multi-hop hop, row, and monotonic time budget tests."""

import pytest

from app.db.query.models import QueryExecutionResult
from app.nlp2sql.multihop.budget import HopAllowance, MultiHopBudget
from app.nlp2sql.multihop.exceptions import MultiHopBudgetExceededError
from app.nlp2sql.multihop.executor import BudgetedQueryExecutor
from tests.nlp2sql.multihop.helpers import RecordingBoundedExecutor


class MutableClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def _budget(clock: MutableClock, **overrides: object) -> MultiHopBudget:
    values = {
        "hops_planned": 2,
        "max_hops": 3,
        "max_rows_per_hop": 2,
        "total_row_budget": 3,
        "total_timeout_seconds": 10.0,
        "query_timeout_ms": 5_000,
        "clock": clock,
    }
    values.update(overrides)
    return MultiHopBudget(**values)


def test_hop_and_total_row_budgets_are_enforced() -> None:
    clock = MutableClock()
    budget = _budget(clock)
    first = budget.allowance_for_next_hop()
    budget.record_hop(2, first)
    second = budget.allowance_for_next_hop()

    assert first.max_rows == 2
    assert second.max_rows == 1
    budget.record_hop(1, second)
    with pytest.raises(MultiHopBudgetExceededError, match="row budget"):
        budget.allowance_for_next_hop()


def test_total_timeout_uses_injected_monotonic_clock() -> None:
    clock = MutableClock()
    budget = _budget(clock, total_timeout_seconds=2.0)
    clock.now = 2.1

    with pytest.raises(MultiHopBudgetExceededError, match="timeout"):
        budget.allowance_for_next_hop()


def test_budgeted_executor_pushes_limits_down_and_truncates_defensively() -> None:
    raw = QueryExecutionResult(
        columns=["value"],
        rows=[{"value": 1}, {"value": 2}, {"value": 3}],
        row_count=3,
        truncated=False,
        elapsed_ms=1,
    )
    executor = RecordingBoundedExecutor([raw])

    result = BudgetedQueryExecutor(executor).execute(
        "SELECT value",
        HopAllowance(max_rows=2, timeout_ms=123),
    )

    assert executor.calls == [("SELECT value", 2, 123)]
    assert result.row_count == 2
    assert result.truncated is True
