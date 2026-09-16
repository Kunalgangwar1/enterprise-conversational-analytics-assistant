"""Unified authenticated conversational endpoint over the chat orchestrator."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response

from app.advanced_reasoning.exceptions import AdvancedReasoningError
from app.api.errors import APIError, APIErrorResponse
from app.api.session_context import (
    get_session_service,
    resolve_request_identity,
    session_storage_api_error,
    set_browser_cookie,
)
from app.auth.dependencies import require_permission
from app.auth.exceptions import PermissionDeniedError
from app.auth.models import AuthPrincipal
from app.auth.permissions import Permission
from app.chat.exceptions import (
    ChatSQLGenerationError,
    InvalidChatStrategyError,
    SpecialistUnavailableError,
)
from app.chat.factory import build_chat_orchestrator
from app.chat.models import ChatRequest, ChatResponse
from app.chat.orchestrator import ChatOrchestrator
from app.data_discovery.exceptions import DataDiscoveryError
from app.data_quality.exceptions import DataQualityError
from app.forecasting.exceptions import ForecastingError
from app.knowledge_catalog.exceptions import KnowledgeCatalogError
from app.llm.exceptions import LLMError
from app.nlp2sql.exceptions import NLP2SQLError
from app.nlp2sql.multihop.exceptions import MultiHopError
from app.routing.exceptions import RoutingError
from app.semantica.exceptions import SemanticaError
from app.sessions.exceptions import SessionStoreError

router = APIRouter(prefix="/chat", tags=["chat"])
ChatPrincipal = Annotated[
    AuthPrincipal,
    Depends(require_permission(Permission.CHAT_USE)),
]


@router.post(
    "",
    response_model=ChatResponse,
    responses={
        400: {"model": APIErrorResponse},
        409: {"model": APIErrorResponse},
        500: {"model": APIErrorResponse},
        503: {"model": APIErrorResponse},
    },
)
def chat(
    payload: ChatRequest,
    request: Request,
    response: Response,
    principal: ChatPrincipal,
) -> ChatResponse:
    """Execute one tab-isolated turn and persist only user-facing conversation state."""

    settings, resolved = resolve_request_identity(request, principal)
    service = get_session_service(request)
    try:
        state = service.get_or_create(resolved.identity)
        turn = _get_orchestrator(request).run(payload, state, principal)
        service.complete_turn(
            resolved.identity,
            user_content=payload.message,
            assistant_content=turn.response.content,
            last_generated_sql=turn.accepted_sql,
            last_token_mapping=(
                {item.token: item.original_value for item in turn.token_mappings}
                if turn.token_mappings
                else None
            ),
            follow_up_questions=list(turn.response.follow_up_questions),
        )
    except InvalidChatStrategyError as exc:
        raise APIError(status_code=400, code="invalid_chat_strategy", message=str(exc)) from exc
    except PermissionDeniedError as exc:
        raise APIError(
            status_code=403,
            code="permission_denied",
            message="You do not have permission to perform this action.",
        ) from exc
    except ChatSQLGenerationError as exc:
        raise APIError(
            status_code=409,
            code="sql_generation_rejected",
            message="The request did not produce validated SQL.",
        ) from exc
    except SpecialistUnavailableError as exc:
        raise APIError(
            status_code=503,
            code="specialist_unavailable",
            message=str(exc),
        ) from exc
    except SessionStoreError as exc:
        raise session_storage_api_error(exc) from exc
    except (LLMError, RoutingError) as exc:
        raise APIError(
            status_code=503,
            code="provider_unavailable",
            message="The configured AI provider is unavailable for this request.",
        ) from exc
    except (
        AdvancedReasoningError,
        DataDiscoveryError,
        DataQualityError,
        ForecastingError,
        KnowledgeCatalogError,
        MultiHopError,
        NLP2SQLError,
        SemanticaError,
    ) as exc:
        raise APIError(
            status_code=500,
            code="specialist_failed",
            message="The selected specialist could not complete the request safely.",
        ) from exc

    set_browser_cookie(response, settings, resolved)
    return turn.response


def _get_orchestrator(request: Request) -> ChatOrchestrator:
    orchestrator: ChatOrchestrator | None = request.app.state.chat_orchestrator
    if orchestrator is None:
        orchestrator = build_chat_orchestrator(
            request.app.state.settings,
            knowledge_catalog_agent=request.app.state.knowledge_catalog_agent,
            data_discovery_service=request.app.state.data_discovery_service,
            data_quality_agent=request.app.state.data_quality_agent,
            semantica_agent=request.app.state.semantica_agent,
        )
        request.app.state.chat_orchestrator = orchestrator
    return orchestrator
