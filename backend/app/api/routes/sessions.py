"""Stateful API contracts for per-tab mode selection and reset."""

from typing import Literal

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, ConfigDict

from app.api.errors import APIError, APIErrorResponse
from app.api.session_context import (
    get_session_service,
    resolve_request_identity,
    session_storage_api_error,
    set_browser_cookie,
)
from app.core.chat_modes import ChatModeKey, UnsupportedChatModeError
from app.sessions.exceptions import SessionStoreError

router = APIRouter(prefix="/chat", tags=["sessions"])


class SelectModeRequest(BaseModel):
    """Canonical mode requested for the current browser tab."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    mode: str


class SelectModeResponse(BaseModel):
    """Public acknowledgment of the current tab's selected mode."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    mode: ChatModeKey
    display_name: str


class ResetSessionResponse(BaseModel):
    """Public acknowledgment that conversational state was cleared."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["reset"] = "reset"
    mode: ChatModeKey


@router.post(
    "/select-mode",
    response_model=SelectModeResponse,
    responses={
        400: {"model": APIErrorResponse},
        500: {"model": APIErrorResponse},
    },
)
def select_mode(
    payload: SelectModeRequest,
    request: Request,
    response: Response,
) -> SelectModeResponse:
    """Persist a canonical mode for the current browser-tab session."""

    settings, resolved = resolve_request_identity(request)
    service = get_session_service(request)
    try:
        selection = service.select_mode(resolved.identity, payload.mode)
    except UnsupportedChatModeError as exc:
        raise APIError(
            status_code=400,
            code="invalid_chat_mode",
            message=str(exc),
        ) from exc
    except SessionStoreError as exc:
        raise session_storage_api_error() from exc

    set_browser_cookie(response, settings, resolved)
    return SelectModeResponse(
        mode=selection.mode.key,
        display_name=selection.mode.display_name,
    )


@router.post(
    "/reset",
    response_model=ResetSessionResponse,
    responses={
        400: {"model": APIErrorResponse},
        500: {"model": APIErrorResponse},
    },
)
def reset_session(request: Request, response: Response) -> ResetSessionResponse:
    """Clear conversational fields for only the current browser tab."""

    settings, resolved = resolve_request_identity(request)
    try:
        state = get_session_service(request).reset(resolved.identity)
    except SessionStoreError as exc:
        raise session_storage_api_error() from exc

    set_browser_cookie(response, settings, resolved)
    return ResetSessionResponse(mode=state.selected_mode)
