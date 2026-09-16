"""Unit coverage for deterministic dashboard calculations and privacy boundaries."""

from datetime import date

import pytest

from app.dashboards.exceptions import DashboardDateRangeError
from app.dashboards.service import DashboardService
from tests.dashboards.fakes import StubDashboardRepository


def test_omitted_dates_use_dataset_relative_twelve_month_range() -> None:
    repository = StubDashboardRepository()
    result = DashboardService(repository).overview()

    assert result.start_date == date(2024, 12, 31)
    assert result.end_date == date(2025, 12, 31)
    assert result.data_as_of == date(2025, 12, 31)
    assert result.available_start_date == date(2024, 1, 1)


def test_overview_values_money_and_previous_comparison_are_exact() -> None:
    result = DashboardService(StubDashboardRepository()).overview("2025-01-01", "2025-12-31")
    by_id = {item.id: item for item in result.kpis}

    assert by_id["total_claims"].value == 10
    assert by_id["total_paid_amount"].value == 250.5
    assert by_id["total_allowed_amount"].value == 301.0
    assert by_id["total_claims"].comparison == 100.0


def test_previous_zero_has_no_misleading_infinite_comparison() -> None:
    repository = StubDashboardRepository()
    result = DashboardService(repository).overview("2024-01-01", "2024-12-30")
    assert all(item.comparison is None for item in result.kpis)


@pytest.mark.parametrize(
    ("start_date", "end_date"),
    [("not-a-date", "2025-01-01"), ("2025-01-01", "31-12-2025")],
)
def test_malformed_dates_are_rejected(start_date: str, end_date: str) -> None:
    with pytest.raises(DashboardDateRangeError, match="valid ISO date"):
        DashboardService(StubDashboardRepository()).overview(start_date, end_date)


def test_reversed_date_range_is_rejected() -> None:
    with pytest.raises(DashboardDateRangeError, match="on or before"):
        DashboardService(StubDashboardRepository()).overview("2025-02-01", "2025-01-01")


def test_claim_aggregates_are_chronological_and_use_fixture_categories() -> None:
    result = DashboardService(StubDashboardRepository()).claims("2025-01-01", "2025-12-31")
    assert [point.period for point in result.monthly_trend] == sorted(
        point.period for point in result.monthly_trend
    )
    assert sum(point.claim_count for point in result.monthly_trend) == 10
    assert {item.category for item in result.status_distribution} == {"paid", "denied"}
    assert result.specialty_breakdown[0].category == "Primary Care"
    assert result.facility_breakdown[0].category == "Clinic"


def test_operations_aggregates_are_chronological_and_correct() -> None:
    result = DashboardService(StubDashboardRepository()).operations("2025-01-01", "2025-12-31")
    assert [point.period for point in result.appointments_by_month] == sorted(
        point.period for point in result.appointments_by_month
    )
    assert sum(point.value for point in result.appointments_by_month) == 12
    assert {item.category: item.count for item in result.appointment_status_distribution} == {
        "completed": 9,
        "no_show": 3,
    }


def test_valid_empty_range_returns_typed_empty_sections() -> None:
    repository = StubDashboardRepository()
    repository.empty = True
    service = DashboardService(repository)

    overview = service.overview("2035-01-01", "2035-12-31")
    claims = service.claims("2035-01-01", "2035-12-31")
    operations = service.operations("2035-01-01", "2035-12-31")

    assert overview.has_data is False
    assert all(item.value == 0 for item in overview.kpis)
    assert claims.has_data is False and claims.monthly_trend == ()
    assert operations.has_data is False and operations.appointments_by_month == ()


def test_responses_expose_aggregates_only() -> None:
    response = DashboardService(StubDashboardRepository()).claims()
    serialized = response.model_dump_json()
    for prohibited in (
        "member_external_id",
        "first_name",
        "last_name",
        "email",
        "phone",
        "token_mapping",
        "resolved_sql",
    ):
        assert prohibited not in serialized
