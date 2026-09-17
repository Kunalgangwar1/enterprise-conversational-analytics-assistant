"""Deterministic dashboard orchestration and exact aggregate calculations."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from app.dashboards.exceptions import (
    DashboardDataUnavailableError,
    DashboardDateRangeError,
)
from app.dashboards.models import (
    CategoryMetric,
    ClaimsDashboardResponse,
    ClaimsTrendPoint,
    DashboardKPI,
    DashboardOverviewResponse,
    DashboardUnit,
    OperationsDashboardResponse,
    TimeSeriesPoint,
)
from app.dashboards.repository import DashboardRepository


@dataclass(frozen=True, slots=True)
class ResolvedDashboardRange:
    start_date: date
    end_date: date
    available_start_date: date
    data_as_of: date

    @property
    def previous(self) -> tuple[date, date]:
        duration = (self.end_date - self.start_date).days + 1
        previous_end = self.start_date - timedelta(days=1)
        return previous_end - timedelta(days=duration - 1), previous_end


class DashboardService:
    """Build aggregate dashboard responses without conversational or model services."""

    def __init__(self, repository: DashboardRepository) -> None:
        self._repository = repository

    def close(self) -> None:
        """Release database resources owned by the dashboard repository."""

        self._repository.close()

    def overview(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> DashboardOverviewResponse:
        resolved = self._resolve_range(start_date, end_date)
        current = self._repository.overview(resolved.start_date, resolved.end_date)
        previous_start, previous_end = resolved.previous
        previous = self._repository.overview(previous_start, previous_end)
        fields = (
            ("total_claims", "Total claims", DashboardUnit.COUNT),
            ("total_paid_amount", "Total paid amount", DashboardUnit.CURRENCY),
            ("total_allowed_amount", "Total allowed amount", DashboardUnit.CURRENCY),
            ("average_paid_amount", "Average paid per claim", DashboardUnit.CURRENCY),
            ("unique_members", "Members represented", DashboardUnit.COUNT),
            ("total_encounters", "Total encounters", DashboardUnit.COUNT),
            ("total_appointments", "Total appointments", DashboardUnit.COUNT),
            ("provider_count", "Providers represented", DashboardUnit.COUNT),
            ("facility_count", "Facilities represented", DashboardUnit.COUNT),
        )
        kpis = tuple(
            DashboardKPI(
                id=key,
                label=label,
                value=self._json_number(current.get(key, 0), unit),
                unit=unit,
                comparison=self._percentage_change(current.get(key), previous.get(key)),
            )
            for key, label, unit in fields
        )
        return DashboardOverviewResponse(
            **self._metadata(resolved, any(self._decimal(item.value) != 0 for item in kpis)),
            kpis=kpis,
        )

    def claims(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> ClaimsDashboardResponse:
        resolved = self._resolve_range(start_date, end_date)
        trends = tuple(
            ClaimsTrendPoint(
                period=row["period"],
                claim_count=int(row["claim_count"]),
                paid_amount=float(self._decimal(row["paid_amount"])),
                allowed_amount=float(self._decimal(row["allowed_amount"])),
            )
            for row in self._repository.claims_trend(resolved.start_date, resolved.end_date)
        )
        statuses = self._categories(
            self._repository.claim_statuses(resolved.start_date, resolved.end_date)
        )
        specialties = self._categories(
            self._repository.claim_specialties(resolved.start_date, resolved.end_date)
        )
        facilities = self._categories(
            self._repository.claim_facilities(resolved.start_date, resolved.end_date)
        )
        return ClaimsDashboardResponse(
            **self._metadata(resolved, bool(trends or statuses or specialties or facilities)),
            monthly_trend=trends,
            status_distribution=statuses,
            specialty_breakdown=specialties,
            facility_breakdown=facilities,
        )

    def operations(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> OperationsDashboardResponse:
        resolved = self._resolve_range(start_date, end_date)
        encounters = self._time_series(
            self._repository.encounters_trend(resolved.start_date, resolved.end_date)
        )
        appointments = self._time_series(
            self._repository.appointments_trend(resolved.start_date, resolved.end_date)
        )
        appointment_statuses = self._categories(
            self._repository.appointment_statuses(resolved.start_date, resolved.end_date)
        )
        encounter_types = self._categories(
            self._repository.encounter_types(resolved.start_date, resolved.end_date)
        )
        appointment_specialties = self._categories(
            self._repository.appointment_specialties(resolved.start_date, resolved.end_date)
        )
        return OperationsDashboardResponse(
            **self._metadata(
                resolved,
                bool(
                    encounters
                    or appointments
                    or appointment_statuses
                    or encounter_types
                    or appointment_specialties
                ),
            ),
            encounters_by_month=encounters,
            appointments_by_month=appointments,
            appointment_status_distribution=appointment_statuses,
            encounter_type_distribution=encounter_types,
            appointments_by_specialty=appointment_specialties,
        )

    def _resolve_range(
        self,
        start_date: str | None,
        end_date: str | None,
    ) -> ResolvedDashboardRange:
        availability = self._repository.data_availability()
        available_start = availability.get("available_start_date")
        data_as_of = availability.get("data_as_of")
        if not isinstance(available_start, date) or not isinstance(data_as_of, date):
            raise DashboardDataUnavailableError(
                "No dated synthetic records are available for dashboard defaults"
            )

        parsed_end = self._parse_date(end_date, "end_date") if end_date else data_as_of
        default_start = max(available_start, self._twelve_months_before(parsed_end))
        parsed_start = self._parse_date(start_date, "start_date") if start_date else default_start
        if parsed_start > parsed_end:
            raise DashboardDateRangeError("start_date must be on or before end_date")
        return ResolvedDashboardRange(
            start_date=parsed_start,
            end_date=parsed_end,
            available_start_date=available_start,
            data_as_of=data_as_of,
        )

    @staticmethod
    def _parse_date(raw: str, field_name: str) -> date:
        try:
            return date.fromisoformat(raw)
        except ValueError as exc:
            raise DashboardDateRangeError(
                f"{field_name} must be a valid ISO date in YYYY-MM-DD format"
            ) from exc

    @staticmethod
    def _twelve_months_before(value: date) -> date:
        try:
            return value.replace(year=value.year - 1)
        except ValueError:
            return value.replace(year=value.year - 1, day=28)

    @staticmethod
    def _decimal(value: object) -> Decimal:
        if value is None:
            return Decimal(0)
        return value if isinstance(value, Decimal) else Decimal(str(value))

    @classmethod
    def _percentage_change(cls, current: object, previous: object) -> float | None:
        previous_value = cls._decimal(previous)
        if previous_value == 0:
            return None
        change = (cls._decimal(current) - previous_value) / previous_value * Decimal(100)
        return float(change.quantize(Decimal("0.1")))

    @classmethod
    def _json_number(cls, value: object, unit: DashboardUnit) -> int | float:
        exact = cls._decimal(value)
        return int(exact) if unit is DashboardUnit.COUNT else float(exact)

    @classmethod
    def _categories(cls, rows: Sequence[Mapping[str, Any]]) -> tuple[CategoryMetric, ...]:
        return tuple(
            CategoryMetric(
                category=str(row["category"]),
                count=int(row["count"]),
                amount=(
                    float(cls._decimal(row["amount"])) if row.get("amount") is not None else None
                ),
                average_amount=(
                    float(cls._decimal(row["average_amount"]))
                    if row.get("average_amount") is not None
                    else None
                ),
            )
            for row in rows
        )

    @staticmethod
    def _time_series(rows: Sequence[Mapping[str, Any]]) -> tuple[TimeSeriesPoint, ...]:
        return tuple(TimeSeriesPoint(period=row["period"], value=int(row["value"])) for row in rows)

    @staticmethod
    def _metadata(resolved: ResolvedDashboardRange, has_data: bool) -> dict[str, object]:
        return {
            "start_date": resolved.start_date,
            "end_date": resolved.end_date,
            "data_as_of": resolved.data_as_of,
            "available_start_date": resolved.available_start_date,
            "available_end_date": resolved.data_as_of,
            "has_data": has_data,
        }
