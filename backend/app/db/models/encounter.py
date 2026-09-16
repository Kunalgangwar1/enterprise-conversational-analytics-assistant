"""Synthetic healthcare encounter model."""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.facility import Facility
    from app.db.models.member import Member
    from app.db.models.provider import Provider


class Encounter(Base):
    """A synthetic member interaction with a provider."""

    __tablename__ = "encounters"
    __table_args__ = (
        UniqueConstraint("encounter_external_id"),
        CheckConstraint(
            "encounter_type IN ('outpatient', 'inpatient', 'emergency', 'telehealth')",
            name="encounter_type_valid",
        ),
        CheckConstraint(
            "status IN ('completed', 'cancelled', 'in_progress')",
            name="encounter_status_valid",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    encounter_external_id: Mapped[str] = mapped_column(String(20), index=True)
    member_id: Mapped[int] = mapped_column(ForeignKey("members.id"), index=True)
    provider_id: Mapped[int] = mapped_column(ForeignKey("providers.id"), index=True)
    facility_id: Mapped[int] = mapped_column(ForeignKey("facilities.id"), index=True)
    encounter_date: Mapped[date] = mapped_column(Date, index=True)
    encounter_type: Mapped[str] = mapped_column(String(30))
    primary_diagnosis_code: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(30))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    member: Mapped[Member] = relationship()
    provider: Mapped[Provider] = relationship()
    facility: Mapped[Facility] = relationship()
