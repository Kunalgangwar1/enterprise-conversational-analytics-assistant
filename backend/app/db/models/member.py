"""Synthetic healthcare member model."""

from datetime import date, datetime

from sqlalchemy import Date, DateTime, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Member(Base):
    """A synthetic enrolled healthcare member."""

    __tablename__ = "members"
    __table_args__ = (UniqueConstraint("member_external_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    member_external_id: Mapped[str] = mapped_column(String(20), index=True)
    first_name: Mapped[str] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100))
    date_of_birth: Mapped[date] = mapped_column(Date)
    sex_at_birth: Mapped[str] = mapped_column(String(20))
    state: Mapped[str] = mapped_column(String(2))
    email: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(30))
    enrollment_start: Mapped[date] = mapped_column(Date)
    enrollment_end: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
