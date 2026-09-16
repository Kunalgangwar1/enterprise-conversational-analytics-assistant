"""Unit tests for SQLAlchemy healthcare model metadata."""

import pytest
from sqlalchemy import Float, Numeric, UniqueConstraint

import app.db.models  # noqa: F401
from app.db.base import Base
from app.db.models import Claim, ClaimLine

EXPECTED_COLUMNS = {
    "members": {
        "id",
        "member_external_id",
        "first_name",
        "last_name",
        "date_of_birth",
        "sex_at_birth",
        "state",
        "email",
        "phone",
        "enrollment_start",
        "enrollment_end",
        "created_at",
    },
    "facilities": {
        "id",
        "facility_external_id",
        "name",
        "facility_type",
        "city",
        "state",
        "created_at",
    },
    "providers": {
        "id",
        "provider_external_id",
        "synthetic_npi",
        "first_name",
        "last_name",
        "specialty",
        "facility_id",
        "created_at",
    },
    "encounters": {
        "id",
        "encounter_external_id",
        "member_id",
        "provider_id",
        "facility_id",
        "encounter_date",
        "encounter_type",
        "primary_diagnosis_code",
        "status",
        "created_at",
    },
    "claims": {
        "id",
        "claim_external_id",
        "member_id",
        "provider_id",
        "encounter_id",
        "service_date",
        "submitted_amount",
        "allowed_amount",
        "paid_amount",
        "claim_status",
        "payer_type",
        "created_at",
    },
    "claim_lines": {
        "id",
        "claim_id",
        "line_number",
        "procedure_code",
        "diagnosis_code",
        "service_units",
        "billed_amount",
        "allowed_amount",
        "paid_amount",
        "created_at",
    },
    "appointments": {
        "id",
        "appointment_external_id",
        "member_id",
        "provider_id",
        "facility_id",
        "scheduled_at",
        "status",
        "reason_category",
        "created_at",
    },
}

EXPECTED_FOREIGN_KEYS = {
    "providers": {"facilities.id"},
    "encounters": {"members.id", "providers.id", "facilities.id"},
    "claims": {"members.id", "providers.id", "encounters.id"},
    "claim_lines": {"claims.id"},
    "appointments": {"members.id", "providers.id", "facilities.id"},
}


def test_metadata_contains_all_expected_tables() -> None:
    assert set(Base.metadata.tables) == set(EXPECTED_COLUMNS)


@pytest.mark.parametrize(("table_name", "expected_columns"), EXPECTED_COLUMNS.items())
def test_tables_contain_expected_columns(table_name: str, expected_columns: set[str]) -> None:
    assert set(Base.metadata.tables[table_name].columns.keys()) == expected_columns


def test_primary_and_foreign_key_metadata() -> None:
    for table in Base.metadata.tables.values():
        assert tuple(column.name for column in table.primary_key.columns) == ("id",)

    for table_name, expected_targets in EXPECTED_FOREIGN_KEYS.items():
        actual_targets = {
            foreign_key.target_fullname
            for foreign_key in Base.metadata.tables[table_name].foreign_keys
        }
        assert actual_targets == expected_targets


def test_claim_line_number_is_unique_within_claim() -> None:
    unique_column_groups = {
        tuple(constraint.columns.keys())
        for constraint in ClaimLine.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
    }
    assert ("claim_id", "line_number") in unique_column_groups


@pytest.mark.parametrize(
    ("model", "column_names"),
    [
        (Claim, ("submitted_amount", "allowed_amount", "paid_amount")),
        (ClaimLine, ("billed_amount", "allowed_amount", "paid_amount")),
    ],
)
def test_monetary_columns_use_exact_numeric_types(
    model: type[Claim] | type[ClaimLine], column_names: tuple[str, ...]
) -> None:
    for column_name in column_names:
        column_type = model.__table__.columns[column_name].type
        assert isinstance(column_type, Numeric)
        assert not isinstance(column_type, Float)
        assert column_type.precision == 12
        assert column_type.scale == 2
