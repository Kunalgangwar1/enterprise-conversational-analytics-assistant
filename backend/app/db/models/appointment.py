"""Synthetic healthcare appointment model."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.facility import Facility
    from app.db.models.member import Member
    from app.db.models.provider import Provider


class Appointment(Base):
    """A synthetic scheduled member appointment."""

    __tablename__ = "appointments"
    __table_args__ = (
        UniqueConstraint("appointment_external_id"),
        CheckConstraint(
            "status IN ('scheduled', 'completed', 'cancelled', 'no_show')",
            name="appointment_status_valid",
        ),
        CheckConstraint(
            "reason_category IN ('preventive', 'new_symptom', 'follow_up', "
            "'chronic_care', 'procedure')",
            name="appointment_reason_valid",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    appointment_external_id: Mapped[str] = mapped_column(String(20), index=True)
    member_id: Mapped[int] = mapped_column(ForeignKey("members.id"), index=True)
    provider_id: Mapped[int] = mapped_column(ForeignKey("providers.id"), index=True)
    facility_id: Mapped[int] = mapped_column(ForeignKey("facilities.id"), index=True)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[str] = mapped_column(String(30))
    reason_category: Mapped[str] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    member: Mapped[Member] = relationship()
    provider: Mapped[Provider] = relationship()
    facility: Mapped[Facility] = relationship()
