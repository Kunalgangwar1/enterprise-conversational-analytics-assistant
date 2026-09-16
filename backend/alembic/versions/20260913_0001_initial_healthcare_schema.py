"""Create the Phase 3 synthetic healthcare schema.

Revision ID: 20260913_0001
Revises:
Create Date: 2026-09-13
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260913_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create all Phase 3 tables, constraints, and indexes."""
    op.create_table(
        "members",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("member_external_id", sa.String(length=20), nullable=False),
        sa.Column("first_name", sa.String(length=100), nullable=False),
        sa.Column("last_name", sa.String(length=100), nullable=False),
        sa.Column("date_of_birth", sa.Date(), nullable=False),
        sa.Column("sex_at_birth", sa.String(length=20), nullable=False),
        sa.Column("state", sa.String(length=2), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("phone", sa.String(length=30), nullable=True),
        sa.Column("enrollment_start", sa.Date(), nullable=False),
        sa.Column("enrollment_end", sa.Date(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_members")),
        sa.UniqueConstraint("member_external_id", name=op.f("uq_members_member_external_id")),
    )
    op.create_index(
        op.f("ix_members_member_external_id"), "members", ["member_external_id"], unique=False
    )

    op.create_table(
        "facilities",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("facility_external_id", sa.String(length=20), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("facility_type", sa.String(length=50), nullable=False),
        sa.Column("city", sa.String(length=100), nullable=False),
        sa.Column("state", sa.String(length=2), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "facility_type IN ('Hospital', 'Clinic', 'Urgent Care', 'Ambulatory Center')",
            name=op.f("ck_facilities_facility_type_valid"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_facilities")),
        sa.UniqueConstraint(
            "facility_external_id", name=op.f("uq_facilities_facility_external_id")
        ),
    )
    op.create_index(
        op.f("ix_facilities_facility_external_id"),
        "facilities",
        ["facility_external_id"],
        unique=False,
    )

    op.create_table(
        "providers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("provider_external_id", sa.String(length=20), nullable=False),
        sa.Column("synthetic_npi", sa.String(length=10), nullable=False),
        sa.Column("first_name", sa.String(length=100), nullable=False),
        sa.Column("last_name", sa.String(length=100), nullable=False),
        sa.Column("specialty", sa.String(length=100), nullable=False),
        sa.Column("facility_id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "specialty IN ('Primary Care', 'Cardiology', 'Orthopedics', "
            "'Dermatology', 'Neurology', 'Endocrinology')",
            name=op.f("ck_providers_specialty_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["facility_id"],
            ["facilities.id"],
            name=op.f("fk_providers_facility_id_facilities"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_providers")),
        sa.UniqueConstraint("provider_external_id", name=op.f("uq_providers_provider_external_id")),
        sa.UniqueConstraint("synthetic_npi", name=op.f("uq_providers_synthetic_npi")),
    )
    op.create_index(op.f("ix_providers_facility_id"), "providers", ["facility_id"], unique=False)
    op.create_index(
        op.f("ix_providers_provider_external_id"),
        "providers",
        ["provider_external_id"],
        unique=False,
    )

    op.create_table(
        "encounters",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("encounter_external_id", sa.String(length=20), nullable=False),
        sa.Column("member_id", sa.Integer(), nullable=False),
        sa.Column("provider_id", sa.Integer(), nullable=False),
        sa.Column("facility_id", sa.Integer(), nullable=False),
        sa.Column("encounter_date", sa.Date(), nullable=False),
        sa.Column("encounter_type", sa.String(length=30), nullable=False),
        sa.Column("primary_diagnosis_code", sa.String(length=10), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "encounter_type IN ('outpatient', 'inpatient', 'emergency', 'telehealth')",
            name=op.f("ck_encounters_encounter_type_valid"),
        ),
        sa.CheckConstraint(
            "status IN ('completed', 'cancelled', 'in_progress')",
            name=op.f("ck_encounters_encounter_status_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["facility_id"],
            ["facilities.id"],
            name=op.f("fk_encounters_facility_id_facilities"),
        ),
        sa.ForeignKeyConstraint(
            ["member_id"], ["members.id"], name=op.f("fk_encounters_member_id_members")
        ),
        sa.ForeignKeyConstraint(
            ["provider_id"],
            ["providers.id"],
            name=op.f("fk_encounters_provider_id_providers"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_encounters")),
        sa.UniqueConstraint(
            "encounter_external_id", name=op.f("uq_encounters_encounter_external_id")
        ),
    )
    op.create_index(
        op.f("ix_encounters_encounter_date"), "encounters", ["encounter_date"], unique=False
    )
    op.create_index(
        op.f("ix_encounters_encounter_external_id"),
        "encounters",
        ["encounter_external_id"],
        unique=False,
    )
    op.create_index(op.f("ix_encounters_facility_id"), "encounters", ["facility_id"], unique=False)
    op.create_index(op.f("ix_encounters_member_id"), "encounters", ["member_id"], unique=False)
    op.create_index(op.f("ix_encounters_provider_id"), "encounters", ["provider_id"], unique=False)

    op.create_table(
        "claims",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("claim_external_id", sa.String(length=20), nullable=False),
        sa.Column("member_id", sa.Integer(), nullable=False),
        sa.Column("provider_id", sa.Integer(), nullable=False),
        sa.Column("encounter_id", sa.Integer(), nullable=True),
        sa.Column("service_date", sa.Date(), nullable=False),
        sa.Column("submitted_amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("allowed_amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("paid_amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("claim_status", sa.String(length=30), nullable=False),
        sa.Column("payer_type", sa.String(length=30), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "allowed_amount <= submitted_amount",
            name=op.f("ck_claims_allowed_not_above_submitted"),
        ),
        sa.CheckConstraint(
            "allowed_amount >= 0", name=op.f("ck_claims_allowed_amount_non_negative")
        ),
        sa.CheckConstraint(
            "claim_status IN ('submitted', 'pending', 'paid', 'denied', 'adjusted')",
            name=op.f("ck_claims_claim_status_valid"),
        ),
        sa.CheckConstraint("paid_amount >= 0", name=op.f("ck_claims_paid_amount_non_negative")),
        sa.CheckConstraint(
            "paid_amount <= allowed_amount", name=op.f("ck_claims_paid_not_above_allowed")
        ),
        sa.CheckConstraint(
            "payer_type IN ('commercial', 'medicare', 'medicaid', 'self_pay')",
            name=op.f("ck_claims_payer_type_valid"),
        ),
        sa.CheckConstraint(
            "submitted_amount >= 0", name=op.f("ck_claims_submitted_amount_non_negative")
        ),
        sa.ForeignKeyConstraint(
            ["encounter_id"],
            ["encounters.id"],
            name=op.f("fk_claims_encounter_id_encounters"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["member_id"], ["members.id"], name=op.f("fk_claims_member_id_members")
        ),
        sa.ForeignKeyConstraint(
            ["provider_id"], ["providers.id"], name=op.f("fk_claims_provider_id_providers")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_claims")),
        sa.UniqueConstraint("claim_external_id", name=op.f("uq_claims_claim_external_id")),
    )
    op.create_index(
        op.f("ix_claims_claim_external_id"), "claims", ["claim_external_id"], unique=False
    )
    op.create_index(op.f("ix_claims_encounter_id"), "claims", ["encounter_id"], unique=False)
    op.create_index(op.f("ix_claims_member_id"), "claims", ["member_id"], unique=False)
    op.create_index(op.f("ix_claims_provider_id"), "claims", ["provider_id"], unique=False)
    op.create_index(op.f("ix_claims_service_date"), "claims", ["service_date"], unique=False)

    op.create_table(
        "claim_lines",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("claim_id", sa.Integer(), nullable=False),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("procedure_code", sa.String(length=10), nullable=False),
        sa.Column("diagnosis_code", sa.String(length=10), nullable=False),
        sa.Column("service_units", sa.Integer(), nullable=False),
        sa.Column("billed_amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("allowed_amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("paid_amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "allowed_amount <= billed_amount",
            name=op.f("ck_claim_lines_allowed_not_above_billed"),
        ),
        sa.CheckConstraint(
            "allowed_amount >= 0", name=op.f("ck_claim_lines_allowed_amount_non_negative")
        ),
        sa.CheckConstraint(
            "billed_amount >= 0", name=op.f("ck_claim_lines_billed_amount_non_negative")
        ),
        sa.CheckConstraint(
            "paid_amount >= 0", name=op.f("ck_claim_lines_paid_amount_non_negative")
        ),
        sa.CheckConstraint(
            "paid_amount <= allowed_amount",
            name=op.f("ck_claim_lines_paid_not_above_allowed"),
        ),
        sa.CheckConstraint(
            "service_units >= 1", name=op.f("ck_claim_lines_service_units_positive")
        ),
        sa.ForeignKeyConstraint(
            ["claim_id"],
            ["claims.id"],
            name=op.f("fk_claim_lines_claim_id_claims"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_claim_lines")),
        sa.UniqueConstraint("claim_id", "line_number", name=op.f("uq_claim_lines_claim_id")),
    )
    op.create_index(op.f("ix_claim_lines_claim_id"), "claim_lines", ["claim_id"], unique=False)

    op.create_table(
        "appointments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("appointment_external_id", sa.String(length=20), nullable=False),
        sa.Column("member_id", sa.Integer(), nullable=False),
        sa.Column("provider_id", sa.Integer(), nullable=False),
        sa.Column("facility_id", sa.Integer(), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("reason_category", sa.String(length=50), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "reason_category IN ('preventive', 'new_symptom', 'follow_up', "
            "'chronic_care', 'procedure')",
            name=op.f("ck_appointments_appointment_reason_valid"),
        ),
        sa.CheckConstraint(
            "status IN ('scheduled', 'completed', 'cancelled', 'no_show')",
            name=op.f("ck_appointments_appointment_status_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["facility_id"],
            ["facilities.id"],
            name=op.f("fk_appointments_facility_id_facilities"),
        ),
        sa.ForeignKeyConstraint(
            ["member_id"], ["members.id"], name=op.f("fk_appointments_member_id_members")
        ),
        sa.ForeignKeyConstraint(
            ["provider_id"],
            ["providers.id"],
            name=op.f("fk_appointments_provider_id_providers"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_appointments")),
        sa.UniqueConstraint(
            "appointment_external_id", name=op.f("uq_appointments_appointment_external_id")
        ),
    )
    op.create_index(
        op.f("ix_appointments_appointment_external_id"),
        "appointments",
        ["appointment_external_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_appointments_facility_id"), "appointments", ["facility_id"], unique=False
    )
    op.create_index(op.f("ix_appointments_member_id"), "appointments", ["member_id"], unique=False)
    op.create_index(
        op.f("ix_appointments_provider_id"), "appointments", ["provider_id"], unique=False
    )
    op.create_index(
        op.f("ix_appointments_scheduled_at"), "appointments", ["scheduled_at"], unique=False
    )


def downgrade() -> None:
    """Remove all Phase 3 tables in foreign-key-safe order."""
    op.drop_index(op.f("ix_appointments_scheduled_at"), table_name="appointments")
    op.drop_index(op.f("ix_appointments_provider_id"), table_name="appointments")
    op.drop_index(op.f("ix_appointments_member_id"), table_name="appointments")
    op.drop_index(op.f("ix_appointments_facility_id"), table_name="appointments")
    op.drop_index(op.f("ix_appointments_appointment_external_id"), table_name="appointments")
    op.drop_table("appointments")
    op.drop_index(op.f("ix_claim_lines_claim_id"), table_name="claim_lines")
    op.drop_table("claim_lines")
    op.drop_index(op.f("ix_claims_service_date"), table_name="claims")
    op.drop_index(op.f("ix_claims_provider_id"), table_name="claims")
    op.drop_index(op.f("ix_claims_member_id"), table_name="claims")
    op.drop_index(op.f("ix_claims_encounter_id"), table_name="claims")
    op.drop_index(op.f("ix_claims_claim_external_id"), table_name="claims")
    op.drop_table("claims")
    op.drop_index(op.f("ix_encounters_provider_id"), table_name="encounters")
    op.drop_index(op.f("ix_encounters_member_id"), table_name="encounters")
    op.drop_index(op.f("ix_encounters_facility_id"), table_name="encounters")
    op.drop_index(op.f("ix_encounters_encounter_external_id"), table_name="encounters")
    op.drop_index(op.f("ix_encounters_encounter_date"), table_name="encounters")
    op.drop_table("encounters")
    op.drop_index(op.f("ix_providers_provider_external_id"), table_name="providers")
    op.drop_index(op.f("ix_providers_facility_id"), table_name="providers")
    op.drop_table("providers")
    op.drop_index(op.f("ix_facilities_facility_external_id"), table_name="facilities")
    op.drop_table("facilities")
    op.drop_index(op.f("ix_members_member_external_id"), table_name="members")
    op.drop_table("members")
