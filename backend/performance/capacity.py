"""Small, testable deployment capacity calculations."""


def postgres_connection_demand(
    *,
    tasks: int,
    workers_per_task: int,
    pool_size: int,
    max_overflow: int,
    pools_per_worker: int = 1,
) -> int:
    """Return the maximum process-pool connection demand for one service."""

    values = (tasks, workers_per_task, pool_size, pools_per_worker)
    if any(value < 1 for value in values) or max_overflow < 0:
        raise ValueError("capacity inputs must be positive and overflow cannot be negative")
    return tasks * workers_per_task * pools_per_worker * (pool_size + max_overflow)


def validate_connection_budget(*, demand: int, budget: int, reserve: int = 0) -> None:
    """Reject a deployment shape that consumes the explicit PostgreSQL budget."""

    if min(demand, budget, reserve) < 0 or demand + reserve > budget:
        raise ValueError(
            f"PostgreSQL demand {demand} plus reserve {reserve} exceeds budget {budget}"
        )
