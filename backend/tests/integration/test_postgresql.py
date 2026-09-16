"""PostgreSQL migration and relational integration tests."""

from collections.abc import Iterator
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.config import Config
from sqlalchemy import Engine, inspect, select, text
from sqlalchemy.exc import SQLAlchemyError

from alembic import command
from app.core.config import get_settings
from app.db.models import Encounter, Facility, Member, Provider
from app.db.session import create_database_engine

pytestmark = pytest.mark.integration

EXPECTED_TABLES = {
    "alembic_version",
    "members",
    "facilities",
    "providers",
    "encounters",
    "claims",
    "claim_lines",
    "appointments",
}


@pytest.fixture(scope="module")
def postgres_engine() -> Iterator[Engine]:
    settings = get_settings()
    if settings.test_database_url is None:
        pytest.skip("TEST_DATABASE_URL is not configured; PostgreSQL integration tests skipped")

    engine = create_database_engine(str(settings.test_database_url))
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError:
        engine.dispose()
        pytest.fail("Could not connect to the isolated PostgreSQL TEST_DATABASE_URL")

    backend_root = Path(__file__).resolve().parents[2]
    alembic_config = Config(backend_root / "alembic.ini")
    escaped_url = str(settings.test_database_url).replace("%", "%%")
    alembic_config.set_main_option("sqlalchemy.url", escaped_url)
    command.upgrade(alembic_config, "head")

    yield engine
    engine.dispose()


def test_postgresql_connection_and_select_one(postgres_engine: Engine) -> None:
    with postgres_engine.connect() as connection:
        assert connection.scalar(text("SELECT 1")) == 1


def test_expected_tables_exist_after_migration(postgres_engine: Engine) -> None:
    assert EXPECTED_TABLES.issubset(inspect(postgres_engine).get_table_names())


def test_basic_member_encounter_provider_join(postgres_engine: Engine) -> None:
    suffix = uuid4().hex[:8]
    with postgres_engine.connect() as connection:
        transaction = connection.begin()
        try:
            facility_id = connection.execute(
                Facility.__table__.insert()
                .values(
                    facility_external_id=f"TF{suffix}",
                    name="Synthetic Integration Clinic",
                    facility_type="Clinic",
                    city="Test City",
                    state="TX",
                )
                .returning(Facility.id)
            ).scalar_one()
            member_id = connection.execute(
                Member.__table__.insert()
                .values(
                    member_external_id=f"TM{suffix}",
                    first_name="Synthetic",
                    last_name="Member",
                    date_of_birth=date(1980, 1, 1),
                    sex_at_birth="unknown",
                    state="TX",
                    email="synthetic.member@example.invalid",
                    phone="000-000-0000",
                    enrollment_start=date(2024, 1, 1),
                )
                .returning(Member.id)
            ).scalar_one()
            synthetic_npi = f"998{int(suffix, 16) % 10_000_000:07d}"
            provider_id = connection.execute(
                Provider.__table__.insert()
                .values(
                    provider_external_id=f"TP{suffix}",
                    synthetic_npi=synthetic_npi,
                    first_name="Synthetic",
                    last_name="Provider",
                    specialty="Primary Care",
                    facility_id=facility_id,
                )
                .returning(Provider.id)
            ).scalar_one()
            connection.execute(
                Encounter.__table__.insert().values(
                    encounter_external_id=f"TE{suffix}",
                    member_id=member_id,
                    provider_id=provider_id,
                    facility_id=facility_id,
                    encounter_date=date(2025, 1, 15),
                    encounter_type="outpatient",
                    primary_diagnosis_code="SYN-D01",
                    status="completed",
                    created_at=datetime(2025, 1, 15, tzinfo=UTC),
                )
            )

            row = connection.execute(
                select(Member.member_external_id, Provider.provider_external_id)
                .join(Encounter, Encounter.member_id == Member.id)
                .join(Provider, Provider.id == Encounter.provider_id)
                .where(Member.id == member_id)
            ).one()
            assert row == (f"TM{suffix}", f"TP{suffix}")
        finally:
            transaction.rollback()
