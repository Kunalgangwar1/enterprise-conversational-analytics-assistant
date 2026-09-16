"""PostgreSQL integration coverage for deterministic aggregate dashboards."""

from collections.abc import Iterator
from datetime import UTC, date, datetime
from uuid import uuid4

import pytest
from sqlalchemy import Engine, create_engine
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import get_settings
from app.dashboards.repository import DashboardRepository
from app.dashboards.service import DashboardService
from app.db.models import Appointment, Claim, Encounter, Facility, Member, Provider
from app.db.query.postgres import PostgresQueryExecutor

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def dashboard_stack() -> Iterator[tuple[DashboardService, PostgresQueryExecutor]]:
    settings = get_settings()
    if settings.query_test_database_url is None or settings.test_database_url is None:
        pytest.skip("TEST_DATABASE_URL and QUERY_TEST_DATABASE_URL are required")
    query_engine: Engine = create_engine(str(settings.query_test_database_url), pool_pre_ping=True)
    write_engine: Engine = create_engine(str(settings.test_database_url), pool_pre_ping=True)
    try:
        with query_engine.connect() as connection:
            connection.exec_driver_sql("SELECT 1")
    except SQLAlchemyError:
        query_engine.dispose()
        write_engine.dispose()
        pytest.fail("Could not connect to the read-only query test database")

    suffix = uuid4().hex[:8]
    external_ids = _insert_fixture(write_engine, suffix)
    executor = PostgresQueryExecutor(query_engine, max_rows=500, timeout_ms=5_000)
    service = DashboardService(DashboardRepository(executor, top_n=10))
    try:
        yield service, executor
    finally:
        _delete_fixture(write_engine, external_ids)
        query_engine.dispose()
        write_engine.dispose()


def _insert_fixture(engine: Engine, suffix: str) -> dict[str, str]:
    external_ids = {
        "facility": f"DF{suffix}",
        "member": f"DM{suffix}",
        "provider": f"DP{suffix}",
        "encounter": f"DE{suffix}",
        "claim": f"DC{suffix}",
        "appointment": f"DA{suffix}",
    }
    with engine.begin() as connection:
        facility_id = connection.execute(
            Facility.__table__.insert()
            .values(
                facility_external_id=external_ids["facility"],
                name="Synthetic Dashboard Clinic",
                facility_type="Clinic",
                city="Test City",
                state="TX",
            )
            .returning(Facility.id)
        ).scalar_one()
        member_id = connection.execute(
            Member.__table__.insert()
            .values(
                member_external_id=external_ids["member"],
                first_name="Synthetic",
                last_name="Dashboard",
                date_of_birth=date(1985, 1, 1),
                sex_at_birth="unknown",
                state="TX",
                enrollment_start=date(2024, 1, 1),
            )
            .returning(Member.id)
        ).scalar_one()
        provider_id = connection.execute(
            Provider.__table__.insert()
            .values(
                provider_external_id=external_ids["provider"],
                synthetic_npi=f"997{int(suffix, 16) % 10_000_000:07d}",
                first_name="Synthetic",
                last_name="Clinician",
                specialty="Primary Care",
                facility_id=facility_id,
            )
            .returning(Provider.id)
        ).scalar_one()
        encounter_id = connection.execute(
            Encounter.__table__.insert()
            .values(
                encounter_external_id=external_ids["encounter"],
                member_id=member_id,
                provider_id=provider_id,
                facility_id=facility_id,
                encounter_date=date(2025, 2, 10),
                encounter_type="outpatient",
                primary_diagnosis_code="SYN-DASH",
                status="completed",
            )
            .returning(Encounter.id)
        ).scalar_one()
        connection.execute(
            Claim.__table__.insert().values(
                claim_external_id=external_ids["claim"],
                member_id=member_id,
                provider_id=provider_id,
                encounter_id=encounter_id,
                service_date=date(2025, 2, 10),
                submitted_amount=100,
                allowed_amount=80,
                paid_amount=70,
                claim_status="paid",
                payer_type="commercial",
            )
        )
        connection.execute(
            Appointment.__table__.insert().values(
                appointment_external_id=external_ids["appointment"],
                member_id=member_id,
                provider_id=provider_id,
                facility_id=facility_id,
                scheduled_at=datetime(2025, 3, 10, 9, tzinfo=UTC),
                status="completed",
                reason_category="follow_up",
            )
        )
    return external_ids


def _delete_fixture(engine: Engine, external_ids: dict[str, str]) -> None:
    with engine.begin() as connection:
        connection.execute(
            Appointment.__table__.delete().where(
                Appointment.appointment_external_id == external_ids["appointment"]
            )
        )
        connection.execute(
            Claim.__table__.delete().where(Claim.claim_external_id == external_ids["claim"])
        )
        connection.execute(
            Encounter.__table__.delete().where(
                Encounter.encounter_external_id == external_ids["encounter"]
            )
        )
        connection.execute(
            Provider.__table__.delete().where(
                Provider.provider_external_id == external_ids["provider"]
            )
        )
        connection.execute(
            Member.__table__.delete().where(Member.member_external_id == external_ids["member"])
        )
        connection.execute(
            Facility.__table__.delete().where(
                Facility.facility_external_id == external_ids["facility"]
            )
        )


def test_dashboard_overview_reconciles_with_direct_aggregates(
    dashboard_stack: tuple[DashboardService, PostgresQueryExecutor],
) -> None:
    service, executor = dashboard_stack
    overview = service.overview()
    direct = executor.execute(
        "SELECT COUNT(*) AS claim_count, "
        "COALESCE(SUM(paid_amount), 0) AS paid_amount, "
        "COALESCE(SUM(allowed_amount), 0) AS allowed_amount "
        "FROM claims WHERE service_date BETWEEN :start_date AND :end_date",
        parameters={"start_date": overview.start_date, "end_date": overview.end_date},
        max_rows=1,
    ).rows[0]
    kpis = {item.id: item.value for item in overview.kpis}

    assert kpis["total_claims"] == direct["claim_count"]
    assert kpis["total_paid_amount"] == float(direct["paid_amount"])
    assert kpis["total_allowed_amount"] == float(direct["allowed_amount"])
    assert kpis["total_paid_amount"] >= 0
    assert kpis["total_allowed_amount"] >= kpis["total_paid_amount"]


def test_claim_and_appointment_trends_reconcile(
    dashboard_stack: tuple[DashboardService, PostgresQueryExecutor],
) -> None:
    service, executor = dashboard_stack
    overview = service.overview()
    claims = service.claims(overview.start_date.isoformat(), overview.end_date.isoformat())
    operations = service.operations(overview.start_date.isoformat(), overview.end_date.isoformat())
    kpis = {item.id: item.value for item in overview.kpis}

    assert sum(point.claim_count for point in claims.monthly_trend) == kpis["total_claims"]
    assert (
        sum(point.value for point in operations.appointments_by_month) == kpis["total_appointments"]
    )

    before = executor.execute("SELECT COUNT(*) AS count FROM claims", max_rows=1).rows[0]
    service.claims(overview.start_date.isoformat(), overview.end_date.isoformat())
    service.operations(overview.start_date.isoformat(), overview.end_date.isoformat())
    after = executor.execute("SELECT COUNT(*) AS count FROM claims", max_rows=1).rows[0]
    assert after == before
