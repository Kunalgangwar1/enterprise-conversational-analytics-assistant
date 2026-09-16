"""Deterministic dashboard repository fake with aggregate-only fixture data."""

from datetime import date
from decimal import Decimal


class StubDashboardRepository:
    """Expose known aggregates without a database, LLM, cloud, or session dependency."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, date | None, date | None]] = []
        self.empty = False

    def data_availability(self) -> dict[str, object]:
        self.calls.append(("availability", None, None))
        return {
            "available_start_date": date(2024, 1, 1),
            "data_as_of": date(2025, 12, 31),
        }

    def overview(self, start_date: date, end_date: date) -> dict[str, object]:
        self.calls.append(("overview", start_date, end_date))
        if self.empty or end_date < date(2024, 1, 1):
            multiplier = Decimal(0)
        elif end_date <= date(2024, 12, 31):
            multiplier = Decimal(1)
        else:
            multiplier = Decimal(2)
        return {
            "total_claims": int(5 * multiplier),
            "total_paid_amount": Decimal("125.25") * multiplier,
            "total_allowed_amount": Decimal("150.50") * multiplier,
            "average_paid_amount": Decimal("25.05") * multiplier,
            "unique_members": int(4 * multiplier),
            "total_encounters": int(6 * multiplier),
            "total_appointments": int(7 * multiplier),
            "provider_count": int(3 * multiplier),
            "facility_count": int(2 * multiplier),
        }

    def claims_trend(self, start_date: date, end_date: date) -> list[dict[str, object]]:
        self.calls.append(("claims_trend", start_date, end_date))
        if self.empty:
            return []
        return [
            {
                "period": date(2025, 1, 1),
                "claim_count": 3,
                "paid_amount": Decimal("60.25"),
                "allowed_amount": Decimal("75.50"),
            },
            {
                "period": date(2025, 2, 1),
                "claim_count": 7,
                "paid_amount": Decimal("190.25"),
                "allowed_amount": Decimal("225.50"),
            },
        ]

    def claim_statuses(self, start_date: date, end_date: date) -> list[dict[str, object]]:
        self.calls.append(("claim_statuses", start_date, end_date))
        return (
            []
            if self.empty
            else [{"category": "paid", "count": 8}, {"category": "denied", "count": 2}]
        )

    def claim_specialties(self, start_date: date, end_date: date) -> list[dict[str, object]]:
        self.calls.append(("claim_specialties", start_date, end_date))
        return (
            []
            if self.empty
            else [
                {
                    "category": "Primary Care",
                    "count": 8,
                    "amount": Decimal("200.00"),
                    "average_amount": Decimal("25.00"),
                }
            ]
        )

    def claim_facilities(self, start_date: date, end_date: date) -> list[dict[str, object]]:
        self.calls.append(("claim_facilities", start_date, end_date))
        return (
            []
            if self.empty
            else [
                {
                    "category": "Clinic",
                    "count": 6,
                    "amount": Decimal("140.00"),
                    "average_amount": Decimal("23.33"),
                }
            ]
        )

    def encounters_trend(self, start_date: date, end_date: date) -> list[dict[str, object]]:
        self.calls.append(("encounters_trend", start_date, end_date))
        return (
            []
            if self.empty
            else [
                {"period": date(2025, 1, 1), "value": 4},
                {"period": date(2025, 2, 1), "value": 6},
            ]
        )

    def appointments_trend(self, start_date: date, end_date: date) -> list[dict[str, object]]:
        self.calls.append(("appointments_trend", start_date, end_date))
        return (
            []
            if self.empty
            else [
                {"period": date(2025, 1, 1), "value": 5},
                {"period": date(2025, 2, 1), "value": 7},
            ]
        )

    def appointment_statuses(self, start_date: date, end_date: date) -> list[dict[str, object]]:
        self.calls.append(("appointment_statuses", start_date, end_date))
        return (
            []
            if self.empty
            else [
                {"category": "completed", "count": 9},
                {"category": "no_show", "count": 3},
            ]
        )

    def encounter_types(self, start_date: date, end_date: date) -> list[dict[str, object]]:
        self.calls.append(("encounter_types", start_date, end_date))
        return [] if self.empty else [{"category": "outpatient", "count": 10}]

    def appointment_specialties(self, start_date: date, end_date: date) -> list[dict[str, object]]:
        self.calls.append(("appointment_specialties", start_date, end_date))
        return [] if self.empty else [{"category": "Primary Care", "count": 12}]
