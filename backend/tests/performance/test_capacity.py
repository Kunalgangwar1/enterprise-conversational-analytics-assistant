import pytest

from performance.capacity import postgres_connection_demand, validate_connection_budget


def test_connection_demand_models_tasks_workers_and_pool_limits() -> None:
    assert (
        postgres_connection_demand(
            tasks=3, workers_per_task=2, pools_per_worker=2, pool_size=5, max_overflow=5
        )
        == 120
    )


def test_connection_budget_rejects_oversubscription() -> None:
    with pytest.raises(ValueError, match="exceeds budget"):
        validate_connection_budget(demand=90, reserve=20, budget=100)
    validate_connection_budget(demand=80, reserve=20, budget=100)
