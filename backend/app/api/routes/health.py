"""Service health endpoint."""

from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.core.config import Settings

router = APIRouter(prefix="/health", tags=["health"])


class HealthResponse(BaseModel):
    """Response returned by the health endpoint."""

    status: str
    service: str
    environment: str


@router.get("", response_model=HealthResponse)
def health_check(request: Request) -> HealthResponse:
    """Report that the API process is available."""
    settings: Settings = request.app.state.settings
    return HealthResponse(
        status="ok",
        service=settings.app_name,
        environment=settings.app_env,
    )
