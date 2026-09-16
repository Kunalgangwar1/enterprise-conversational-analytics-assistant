"""Repository boundary tests for fixed SQL, bound dates, and bounded categories."""

from collections.abc import Mapping
from datetime import date

from app.dashboards.repository import DashboardRepository
from app.db.query.models import QueryExecutionResult


class RecordingExecutor:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Mapping[str, object] | None, int | None]] = []

    def execute(
        self,
        sql: str,
        *,
        parameters: Mapping[str, object] | None = None,
        max_rows: int | None = None,
        timeout_ms: int | None = None,
    ) -> QueryExecutionResult:
        self.calls.append((sql, parameters, max_rows))
        return QueryExecutionResult([], [], 0, False, 0)


def test_repository_uses_shared_executor_bound_dates_and_top_n() -> None:
    executor = RecordingExecutor()
    repository = DashboardRepository(executor, top_n=7)

    repository.claim_specialties(date(2025, 1, 1), date(2025, 12, 31))

    sql, parameters, max_rows = executor.calls[0]
    assert "JOIN providers" in sql
    assert "LIMIT :top_n" in sql
    assert parameters == {
        "start_date": date(2025, 1, 1),
        "end_date": date(2025, 12, 31),
        "top_n": 7,
    }
    assert max_rows is None


def test_facility_query_uses_real_claim_encounter_facility_relationship() -> None:
    executor = RecordingExecutor()
    repository = DashboardRepository(executor, top_n=10)

    repository.claim_facilities(date(2025, 1, 1), date(2025, 12, 31))

    sql = executor.calls[0][0]
    assert "JOIN encounters AS e ON e.id = c.encounter_id" in sql
    assert "JOIN facilities AS f ON f.id = e.facility_id" in sql
    assert "members" not in sql.lower()
