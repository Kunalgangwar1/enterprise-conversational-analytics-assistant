"""Thin privacy boundary for deterministic Data Discovery."""

from typing import Annotated

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, StringConstraints

from app.api.errors import APIError, APIErrorResponse
from app.data_discovery.exceptions import DataDiscoveryError
from app.data_discovery.factory import build_data_discovery_service
from app.data_discovery.models import DataDiscoveryResult
from app.data_discovery.search import DataDiscoveryService
from app.privacy import PrivacyProcessor

router = APIRouter(prefix="/data-discovery", tags=["data-discovery"])


class DataDiscoveryQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4_000)
    ]


@router.post(
    "/query",
    response_model=DataDiscoveryResult,
    responses={500: {"model": APIErrorResponse}},
)
def query_data_discovery(payload: DataDiscoveryQuery, request: Request) -> DataDiscoveryResult:
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
