"""Public API contract for static canonical chat-mode information."""

from fastapi import APIRouter, Query

from app.api.errors import APIError, APIErrorResponse
from app.core.chat_modes import UnsupportedChatModeError
from app.services.chat_mode_service import ChatModeWelcome, chat_mode_service

router = APIRouter(prefix="/chat-mode", tags=["chat-modes"])


@router.get(
    "/welcome",
    response_model=ChatModeWelcome,
    responses={400: {"model": APIErrorResponse}},
)
def read_chat_mode_welcome(
    mode: str = Query(description="Canonical top-level chat mode"),
) -> ChatModeWelcome:
    """Return static welcome information for one canonical mode."""

    try:
        return chat_mode_service.get_welcome(mode)
    except UnsupportedChatModeError as exc:
        raise APIError(
            status_code=400,
            code="invalid_chat_mode",
            message=str(exc),
        ) from exc
