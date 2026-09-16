"""Synthetic healthcare facility model."""

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Facility(Base):
    """A synthetic location where care is delivered."""

    __tablename__ = "facilities"
    __table_args__ = (
        UniqueConstraint("facility_external_id"),
        CheckConstraint(
            "facility_type IN ('Hospital', 'Clinic', 'Urgent Care', 'Ambulatory Center')",
            name="facility_type_valid",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    facility_external_id: Mapped[str] = mapped_column(String(20), index=True)
    name: Mapped[str] = mapped_column(String(200))
    facility_type: Mapped[str] = mapped_column(String(50))
    city: Mapped[str] = mapped_column(String(100))
    state: Mapped[str] = mapped_column(String(2))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
