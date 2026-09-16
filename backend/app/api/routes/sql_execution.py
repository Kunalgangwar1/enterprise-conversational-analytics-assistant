"""Execute server-owned accepted SQL for one browser-session/tab."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response

from app.api.errors import APIError, APIErrorResponse
from app.api.session_context import (
    get_session_service,
    resolve_request_identity,
    session_storage_api_error,
    set_browser_cookie,
)
from app.auth.dependencies import require_permission
from app.auth.models import AuthPrincipal
from app.auth.permissions import Permission
from app.db.query.exceptions import (
    QueryConfigurationError,
    QueryExecutionError,
    QueryTimeoutError,
    QueryValidationError,
)
from app.nlp2sql.models import SQLValidationDecision
from app.sessions.exceptions import SessionStoreError
from app.sql_results.exceptions import SQLNotValidatedError, SQLTokenResolutionError
from app.sql_results.factory import build_sql_execution_service
from app.sql_results.models import SQLAnalyticsResult
from app.sql_results.service import SQLExecutionService
from app.sql_results.token_resolver import token_mappings_from_session

router = APIRouter(prefix="/chat", tags=["sql-execution"])
SQLPrincipal = Annotated[
    AuthPrincipal,
    Depends(require_permission(Permission.SQL_EXECUTE)),
]


@router.post(
    "/execute-sql",
    response_model=SQLAnalyticsResult,
    responses={
        409: {"model": APIErrorResponse},
        500: {"model": APIErrorResponse},
        503: {"model": APIErrorResponse},
        504: {"model": APIErrorResponse},
    },
)
def execute_sql(
    request: Request,
    response: Response,
    principal: SQLPrincipal,
) -> SQLAnalyticsResult:
    """Execute only the accepted SQL stored by trusted server-side orchestration."""

    settings, resolved = resolve_request_identity(request, principal)
    try:
        state = get_session_service(request).get_or_create(resolved.identity)
    except SessionStoreError as exc:
        raise session_storage_api_error(exc) from exc

    if state.last_generated_sql is None:
        raise APIError(
            status_code=409,
            code="no_validated_sql",
            message="No validated SQL is available for the current conversation.",
        )

    try:
        token_mappings = token_mappings_from_session(state.last_token_mapping)
        service = _get_execution_service(request)
        result = service.execute(
            final_sql=state.last_generated_sql,
            decision=SQLValidationDecision.ACCEPT,
            token_mappings=token_mappings,
        )
    except SQLTokenResolutionError as exc:
        raise APIError(
            status_code=409,
            code="sql_token_resolution_failed",
            message="Stored SQL privacy tokens could not be resolved safely.",
        ) from exc
    except SQLNotValidatedError as exc:
        raise APIError(
            status_code=409,
            code="no_validated_sql",
            message="No validated SQL is available for the current conversation.",
        ) from exc
    except QueryTimeoutError as exc:
        raise APIError(
            status_code=504,
            code="query_timeout",
            message="The analytical query exceeded its execution time limit.",
        ) from exc
    except QueryValidationError as exc:
        raise APIError(
            status_code=409,
            code="sql_execution_rejected",
            message="Stored SQL did not pass the execution safety boundary.",
        ) from exc
    except QueryConfigurationError as exc:
        raise APIError(
            status_code=503,
            code="query_execution_unavailable",
            message="Analytical query execution is not configured.",
        ) from exc
    except QueryExecutionError as exc:
        raise APIError(
            status_code=500,
            code="query_execution_failed",
            message="The analytical query could not be executed.",
        ) from exc

    set_browser_cookie(response, settings, resolved)
    return result


def _get_execution_service(request: Request) -> SQLExecutionService:
    service: SQLExecutionService | None = request.app.state.sql_execution_service
    if service is None:
        service = build_sql_execution_service(request.app.state.settings)
        request.app.state.sql_execution_service = service
    return service
