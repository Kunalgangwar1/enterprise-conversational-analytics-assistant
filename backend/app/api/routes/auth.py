"""Safe current-principal API without exposing tokens or raw provider claims."""

from fastapi import APIRouter

from app.auth.dependencies import CurrentPrincipal
from app.auth.models import AuthMeResponse

router = APIRouter(prefix="/auth", tags=["authentication"])


@router.get("/me", response_model=AuthMeResponse)
def read_current_principal(principal: CurrentPrincipal) -> AuthMeResponse:
    """Return the normalized identity and effective application permissions."""

    return AuthMeResponse.from_principal(principal)
