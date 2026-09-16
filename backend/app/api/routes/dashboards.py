"""Aggregate-only APIs for the separate AI Dashboard surface."""

from fastapi import APIRouter, Depends, Query, Request

from app.api.errors import APIError, APIErrorResponse
from app.auth.dependencies import require_permission
from app.auth.permissions import Permission
from app.dashboards.exceptions import (
    DashboardDataUnavailableError,
    DashboardDateRangeError,
)
from app.dashboards.factory import build_dashboard_service
from app.dashboards.models import (
    ClaimsDashboardResponse,
    DashboardOverviewResponse,
    OperationsDashboardResponse,
)
from app.dashboards.service import DashboardService
from app.db.query.exceptions import (
    QueryConfigurationError,
    QueryExecutionError,
    QueryTimeoutError,
    QueryValidationError,
)

router = APIRouter(
    prefix="/dashboards",
    tags=["dashboards"],
    dependencies=[Depends(require_permission(Permission.DASHBOARD_READ))],
)

_ERROR_RESPONSES = {
    422: {"model": APIErrorResponse},
    500: {"model": APIErrorResponse},
    503: {"model": APIErrorResponse},
    504: {"model": APIErrorResponse},
}


@router.get(
    "/overview",
    response_model=DashboardOverviewResponse,
    responses=_ERROR_RESPONSES,
)
def dashboard_overview(
    request: Request,
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
) -> DashboardOverviewResponse:
    """Return dataset-relative KPI aggregates and previous-period comparisons."""

    return _run(request, "overview", start_date, end_date)


@router.get(
    "/claims",
    response_model=ClaimsDashboardResponse,
    responses=_ERROR_RESPONSES,
)
def claims_dashboard(
    request: Request,
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
) -> ClaimsDashboardResponse:
    """Return monthly claims and bounded aggregate breakdowns."""

    return _run(request, "claims", start_date, end_date)


@router.get(
    "/operations",
    response_model=OperationsDashboardResponse,
    responses=_ERROR_RESPONSES,
)
def operations_dashboard(
    request: Request,
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
) -> OperationsDashboardResponse:
    """Return appointment and encounter operational aggregates."""

    return _run(request, "operations", start_date, end_date)


def _run(
    request: Request,
    section: str,
    start_date: str | None,
    end_date: str | None,
) -> DashboardOverviewResponse | ClaimsDashboardResponse | OperationsDashboardResponse:
    unexpected_parameters = set(request.query_params) - {"start_date", "end_date"}
    if unexpected_parameters:
        raise APIError(
            status_code=422,
            code="invalid_dashboard_parameters",
            message="Dashboard requests accept only start_date and end_date parameters.",
        )
    try:
        service = _get_service(request)
        handler = getattr(service, section)
        return handler(start_date, end_date)
    except DashboardDateRangeError as exc:
        raise APIError(
            status_code=422,
            code="invalid_dashboard_date_range",
            message=str(exc),
        ) from exc
    except DashboardDataUnavailableError as exc:
        raise APIError(
            status_code=503,
            code="dashboard_data_unavailable",
            message="Dashboard date availability could not be determined.",
        ) from exc
    except QueryTimeoutError as exc:
        raise APIError(
            status_code=504,
            code="dashboard_query_timeout",
            message="Dashboard analytics exceeded the execution time limit.",
        ) from exc
    except (QueryConfigurationError, QueryValidationError) as exc:
        raise APIError(
            status_code=503,
            code="dashboard_unavailable",
            message="Dashboard analytics are not currently available.",
        ) from exc
    except QueryExecutionError as exc:
        raise APIError(
            status_code=500,
            code="dashboard_query_failed",
            message="Dashboard analytics could not be loaded.",
        ) from exc


def _get_service(request: Request) -> DashboardService:
    service: DashboardService | None = request.app.state.dashboard_service
    if service is None:
        service = build_dashboard_service(request.app.state.settings)
        request.app.state.dashboard_service = service
    return service
