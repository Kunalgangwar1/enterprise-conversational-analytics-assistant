"""Thin privacy boundary for deterministic Data Discovery."""

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict

from app.api.errors import APIError, APIErrorResponse
from app.auth.dependencies import CurrentPrincipal, require_permission
from app.auth.permissions import Permission
from app.data_discovery.exceptions import DataDiscoveryError
from app.data_discovery.factory import build_data_discovery_service
from app.data_discovery.models import DataDiscoveryResult
from app.data_discovery.search import DataDiscoveryService
from app.privacy import PrivacyProcessor
from app.security.rate_limit import enforce_rate_limit
from app.security.request_limits import UserQuestion

router = APIRouter(
    prefix="/data-discovery",
    tags=["data-discovery"],
    dependencies=[Depends(require_permission(Permission.DATA_DISCOVERY_READ))],
)


class DataDiscoveryQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: UserQuestion


@router.post(
    "/query",
    response_model=DataDiscoveryResult,
    responses={429: {"model": APIErrorResponse}, 500: {"model": APIErrorResponse}},
)
def query_data_discovery(
    payload: DataDiscoveryQuery,
    request: Request,
    principal: CurrentPrincipal,
) -> DataDiscoveryResult:
    enforce_rate_limit(request, principal, "data_discovery")
    safe_question = PrivacyProcessor().process(payload.question).safe_text
    try:
        return _get_service(request).search(safe_question)
    except DataDiscoveryError as exc:
        raise APIError(
            status_code=500,
            code="data_discovery_unavailable",
            message="Data Discovery is not currently available.",
        ) from exc


def _get_service(request: Request) -> DataDiscoveryService:
    service: DataDiscoveryService | None = request.app.state.data_discovery_service
    if service is None:
        service = build_data_discovery_service(request.app.state.settings)
        request.app.state.data_discovery_service = service
    return service
