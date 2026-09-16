"""Typed aggregate-only contracts for the AI Dashboard."""

from datetime import date
from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class DashboardUnit(StrEnum):
    """Display semantics for a raw dashboard numeric value."""

    COUNT = "count"
    CURRENCY = "currency"


class DashboardResponseBase(BaseModel):
    """Dataset-relative date metadata shared by all dashboard sections."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    start_date: date
    end_date: date
    data_as_of: date
    available_start_date: date
    available_end_date: date
    has_data: bool


class DashboardKPI(BaseModel):
    """One raw KPI and optional deterministic previous-period comparison."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    label: str
    value: int | float
    unit: DashboardUnit
    comparison: float | None = None
    comparison_label: str | None = "vs previous period"


class DashboardOverviewResponse(DashboardResponseBase):
    """High-level aggregate metrics for the selected range."""

    kpis: tuple[DashboardKPI, ...]


class ClaimsTrendPoint(BaseModel):
    """Monthly claim volume and monetary aggregates."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    period: date
    claim_count: int
    paid_amount: float
    allowed_amount: float


class CategoryMetric(BaseModel):
    """One bounded aggregate category suitable for charting and tables."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    category: str
    count: int
    amount: float | None = None
    average_amount: float | None = None


class ClaimsDashboardResponse(DashboardResponseBase):
    """Aggregate claims analytics without claim- or member-level rows."""

    monthly_trend: tuple[ClaimsTrendPoint, ...]
    status_distribution: tuple[CategoryMetric, ...]
    specialty_breakdown: tuple[CategoryMetric, ...]
    facility_breakdown: tuple[CategoryMetric, ...]


class TimeSeriesPoint(BaseModel):
    """One chronological aggregate count."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    period: date
    value: int


class OperationsDashboardResponse(DashboardResponseBase):
    """Aggregate appointment and encounter analytics."""

    encounters_by_month: tuple[TimeSeriesPoint, ...]
    appointments_by_month: tuple[TimeSeriesPoint, ...]
    appointment_status_distribution: tuple[CategoryMetric, ...]
    encounter_type_distribution: tuple[CategoryMetric, ...]
    appointments_by_specialty: tuple[CategoryMetric, ...]
