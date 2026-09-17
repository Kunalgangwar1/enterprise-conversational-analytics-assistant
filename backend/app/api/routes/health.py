"""Service health endpoint."""

from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    """Response returned by the health endpoint."""

    status: str


@router.get("/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    """Report that the API process is available."""
    return HealthResponse(status="ok")


@router.get("/ready", response_model=HealthResponse, responses={503: {"description": "Not ready"}})
def readiness_check(request: Request) -> HealthResponse:
    """Report aggregate internal dependency readiness without exposing details."""

    if not request.app.state.readiness_service.is_ready():
        from app.api.errors import APIError

        raise APIError(
            status_code=503,
            code="service_not_ready",
            message="The service is not ready to accept dependent work.",
        )
    return HealthResponse(status="ready")
