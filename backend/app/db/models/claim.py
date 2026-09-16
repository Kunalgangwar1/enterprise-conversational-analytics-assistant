"""Synthetic healthcare claim and claim-line models."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.encounter import Encounter
    from app.db.models.member import Member
    from app.db.models.provider import Provider


class Claim(Base):
    """A synthetic healthcare claim header."""

    __tablename__ = "claims"
    __table_args__ = (
        UniqueConstraint("claim_external_id"),
        CheckConstraint("submitted_amount >= 0", name="submitted_amount_non_negative"),
        CheckConstraint("allowed_amount >= 0", name="allowed_amount_non_negative"),
        CheckConstraint("paid_amount >= 0", name="paid_amount_non_negative"),
        CheckConstraint("allowed_amount <= submitted_amount", name="allowed_not_above_submitted"),
        CheckConstraint("paid_amount <= allowed_amount", name="paid_not_above_allowed"),
        CheckConstraint(
            "claim_status IN ('submitted', 'pending', 'paid', 'denied', 'adjusted')",
            name="claim_status_valid",
        ),
        CheckConstraint(
            "payer_type IN ('commercial', 'medicare', 'medicaid', 'self_pay')",
            name="payer_type_valid",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    claim_external_id: Mapped[str] = mapped_column(String(20), index=True)
    member_id: Mapped[int] = mapped_column(ForeignKey("members.id"), index=True)
    provider_id: Mapped[int] = mapped_column(ForeignKey("providers.id"), index=True)
    encounter_id: Mapped[int | None] = mapped_column(
        ForeignKey("encounters.id", ondelete="SET NULL"), index=True
    )
    service_date: Mapped[date] = mapped_column(Date, index=True)
    submitted_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    allowed_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    paid_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    claim_status: Mapped[str] = mapped_column(String(30))
    payer_type: Mapped[str] = mapped_column(String(30))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    member: Mapped[Member] = relationship()
    provider: Mapped[Provider] = relationship()
    encounter: Mapped[Encounter | None] = relationship()
    lines: Mapped[list[ClaimLine]] = relationship(
        back_populates="claim", cascade="all, delete-orphan"
    )


class ClaimLine(Base):
    """A synthetic service line belonging to a claim."""

    __tablename__ = "claim_lines"
    __table_args__ = (
        UniqueConstraint("claim_id", "line_number"),
        CheckConstraint("service_units >= 1", name="service_units_positive"),
        CheckConstraint("billed_amount >= 0", name="billed_amount_non_negative"),
        CheckConstraint("allowed_amount >= 0", name="allowed_amount_non_negative"),
        CheckConstraint("paid_amount >= 0", name="paid_amount_non_negative"),
        CheckConstraint("allowed_amount <= billed_amount", name="allowed_not_above_billed"),
        CheckConstraint("paid_amount <= allowed_amount", name="paid_not_above_allowed"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    claim_id: Mapped[int] = mapped_column(ForeignKey("claims.id", ondelete="CASCADE"), index=True)
    line_number: Mapped[int] = mapped_column(Integer)
    procedure_code: Mapped[str] = mapped_column(String(10))
    diagnosis_code: Mapped[str] = mapped_column(String(10))
    service_units: Mapped[int] = mapped_column(Integer)
    billed_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    allowed_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    paid_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    claim: Mapped[Claim] = relationship(back_populates="lines")
