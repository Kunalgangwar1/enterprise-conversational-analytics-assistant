"""Application-enforced hop, row, and monotonic time budgets."""

from collections.abc import Callable
from dataclasses import dataclass
from time import monotonic

from app.nlp2sql.multihop.exceptions import MultiHopBudgetExceededError
from app.nlp2sql.multihop.models import MultiHopBudgetSnapshot


@dataclass(frozen=True, slots=True)
class HopAllowance:
    max_rows: int
    timeout_ms: int


class MultiHopBudget:
    """Track and enforce all multi-hop limits outside model prompts."""

    def __init__(
        self,
        *,
        hops_planned: int,
        max_hops: int,
        max_rows_per_hop: int,
        total_row_budget: int,
        total_timeout_seconds: float,
        query_timeout_ms: int,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        if hops_planned < 1 or hops_planned > max_hops:
            raise MultiHopBudgetExceededError("Multi-hop plan violates the hop budget")
        if max_rows_per_hop < 1 or total_row_budget < max_rows_per_hop:
            raise ValueError("Multi-hop row budgets are invalid")
        if total_timeout_seconds <= 0 or query_timeout_ms < 1:
            raise ValueError("Multi-hop timeout budgets are invalid")
        self._hops_planned = hops_planned
        self._max_hops = max_hops
        self._max_rows_per_hop = max_rows_per_hop
        self._total_row_budget = total_row_budget
        self._total_timeout_seconds = total_timeout_seconds
        self._query_timeout_ms = query_timeout_ms
        self._clock = clock
        self._started_at = clock()
        self._rows_per_hop: list[int] = []

    def allowance_for_next_hop(self) -> HopAllowance:
        if len(self._rows_per_hop) >= self._max_hops:
            raise MultiHopBudgetExceededError("Multi-hop maximum hop count is exhausted")
        remaining_rows = self._total_row_budget - sum(self._rows_per_hop)
        if remaining_rows < 1:
            raise MultiHopBudgetExceededError("Multi-hop total row budget is exhausted")
        remaining_seconds = self._total_timeout_seconds - self.elapsed_seconds
        if remaining_seconds <= 0:
            raise MultiHopBudgetExceededError("Multi-hop total timeout is exhausted")
        return HopAllowance(
            max_rows=min(self._max_rows_per_hop, remaining_rows),
            timeout_ms=max(1, min(self._query_timeout_ms, int(remaining_seconds * 1_000))),
        )

    def record_hop(self, row_count: int, allowance: HopAllowance) -> None:
        if row_count < 0 or row_count > allowance.max_rows:
            raise MultiHopBudgetExceededError("A multi-hop result exceeded its row allowance")
        self._rows_per_hop.append(row_count)
        if sum(self._rows_per_hop) > self._total_row_budget:
            raise MultiHopBudgetExceededError("Multi-hop total row budget is exhausted")
        if self.elapsed_seconds > self._total_timeout_seconds:
            raise MultiHopBudgetExceededError("Multi-hop total timeout was exceeded")

    @property
    def elapsed_seconds(self) -> float:
        return max(0.0, self._clock() - self._started_at)

    def snapshot(self) -> MultiHopBudgetSnapshot:
        return MultiHopBudgetSnapshot(
            hops_planned=self._hops_planned,
            hops_executed=len(self._rows_per_hop),
            rows_per_hop=tuple(self._rows_per_hop),
            total_rows_returned=sum(self._rows_per_hop),
            elapsed_seconds=self.elapsed_seconds,
        )
