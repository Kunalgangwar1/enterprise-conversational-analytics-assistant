"""Service health endpoint."""

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/health", tags=["health"])


class HealthResponse(BaseModel):
    """Response returned by the health endpoint."""

    status: str


@router.get("", response_model=HealthResponse)
def health_check() -> HealthResponse:
    """Report that the API process is available."""
    return HealthResponse(status="ok")
