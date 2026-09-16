"""Synthetic healthcare provider model."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.facility import Facility


class Provider(Base):
    """A synthetic clinician associated with a facility."""

    __tablename__ = "providers"
    __table_args__ = (
        UniqueConstraint("provider_external_id"),
        UniqueConstraint("synthetic_npi"),
        CheckConstraint(
            "specialty IN ('Primary Care', 'Cardiology', 'Orthopedics', "
            "'Dermatology', 'Neurology', 'Endocrinology')",
            name="specialty_valid",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    provider_external_id: Mapped[str] = mapped_column(String(20), index=True)
    synthetic_npi: Mapped[str] = mapped_column(String(10))
    first_name: Mapped[str] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100))
    specialty: Mapped[str] = mapped_column(String(100))
    facility_id: Mapped[int] = mapped_column(ForeignKey("facilities.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    facility: Mapped[Facility] = relationship()
