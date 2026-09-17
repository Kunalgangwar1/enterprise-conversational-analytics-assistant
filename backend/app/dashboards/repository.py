"""Read-only repository for fixed aggregate dashboard queries."""

from collections.abc import Mapping
from datetime import date
from typing import Any

from app.dashboards import queries
from app.db.query.base import QueryExecutor


class DashboardRepository:
    """Execute only predefined aggregate SQL through the shared safety boundary."""

    def __init__(self, executor: QueryExecutor, *, top_n: int) -> None:
        self._executor = executor
        self._top_n = top_n

    def data_availability(self) -> Mapping[str, Any]:
        return self._one(queries.DATA_AVAILABILITY_SQL)

    def overview(self, start_date: date, end_date: date) -> Mapping[str, Any]:
        return self._one(queries.OVERVIEW_SQL, self._date_parameters(start_date, end_date))

    def claims_trend(self, start_date: date, end_date: date) -> list[Mapping[str, Any]]:
        return self._many(queries.CLAIMS_TREND_SQL, self._date_parameters(start_date, end_date))

    def claim_statuses(self, start_date: date, end_date: date) -> list[Mapping[str, Any]]:
        return self._many(queries.CLAIM_STATUS_SQL, self._date_parameters(start_date, end_date))

    def claim_specialties(self, start_date: date, end_date: date) -> list[Mapping[str, Any]]:
        return self._many(
            queries.CLAIM_SPECIALTY_SQL, self._bounded_parameters(start_date, end_date)
        )

    def claim_facilities(self, start_date: date, end_date: date) -> list[Mapping[str, Any]]:
        return self._many(
            queries.CLAIM_FACILITY_SQL, self._bounded_parameters(start_date, end_date)
        )

    def encounters_trend(self, start_date: date, end_date: date) -> list[Mapping[str, Any]]:
        return self._many(queries.ENCOUNTERS_TREND_SQL, self._date_parameters(start_date, end_date))

    def appointments_trend(self, start_date: date, end_date: date) -> list[Mapping[str, Any]]:
        return self._many(
            queries.APPOINTMENTS_TREND_SQL, self._date_parameters(start_date, end_date)
        )

    def appointment_statuses(self, start_date: date, end_date: date) -> list[Mapping[str, Any]]:
        return self._many(
            queries.APPOINTMENT_STATUS_SQL,
            self._date_parameters(start_date, end_date),
        )

    def encounter_types(self, start_date: date, end_date: date) -> list[Mapping[str, Any]]:
        return self._many(queries.ENCOUNTER_TYPE_SQL, self._date_parameters(start_date, end_date))

    def appointment_specialties(self, start_date: date, end_date: date) -> list[Mapping[str, Any]]:
        return self._many(
            queries.APPOINTMENT_SPECIALTY_SQL,
            self._bounded_parameters(start_date, end_date),
        )

    def _one(
        self,
        sql: str,
        parameters: Mapping[str, object] | None = None,
    ) -> Mapping[str, Any]:
        result = self._executor.execute(sql, parameters=parameters, max_rows=1)
        return result.rows[0] if result.rows else {}

    def _many(self, sql: str, parameters: Mapping[str, object]) -> list[Mapping[str, Any]]:
        result = self._executor.execute(sql, parameters=parameters)
        return result.rows

    @staticmethod
    def _date_parameters(start_date: date, end_date: date) -> dict[str, object]:
        return {"start_date": start_date, "end_date": end_date}

    def _bounded_parameters(self, start_date: date, end_date: date) -> dict[str, object]:
        return {
            **self._date_parameters(start_date, end_date),
            "top_n": self._top_n,
        }

    def close(self) -> None:
        """Release the repository's analytical query pool."""

        self._executor.close()
