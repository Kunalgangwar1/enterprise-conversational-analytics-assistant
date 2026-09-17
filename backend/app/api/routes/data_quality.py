"""Thin privacy and error boundary for Data Quality guidance."""

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict

from app.api.errors import APIError, APIErrorResponse
from app.auth.dependencies import CurrentPrincipal, require_permission
from app.auth.permissions import Permission
from app.data_quality.agent import DataQualityAgent
from app.data_quality.exceptions import DataQualityError
from app.data_quality.factory import build_data_quality_agent
from app.data_quality.models import DataQualityResult
from app.llm.exceptions import LLMError
from app.privacy import PrivacyProcessor, ResponseUnmasker
from app.reliability.errors import CircuitOpenError
from app.security.rate_limit import enforce_rate_limit
from app.security.request_limits import UserQuestion

router = APIRouter(
    prefix="/data-quality",
    tags=["data-quality"],
    dependencies=[Depends(require_permission(Permission.DATA_QUALITY_READ))],
)


class DataQualityQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: UserQuestion


@router.post(
    "/query",
    response_model=DataQualityResult,
    responses={
        429: {"model": APIErrorResponse},
        500: {"model": APIErrorResponse},
        503: {"model": APIErrorResponse},
    },
)
def query_data_quality(
    payload: DataQualityQuery,
    request: Request,
    principal: CurrentPrincipal,
) -> DataQualityResult:
    enforce_rate_limit(request, principal, "data_quality")
    privacy = PrivacyProcessor().process(payload.question)
    try:
        result = _get_agent(request).answer(privacy.safe_text)
        answer = ResponseUnmasker().unmask(result.answer, privacy.token_mappings)
    except DataQualityError as exc:
        raise APIError(
            status_code=500,
            code="data_quality_invalid_response",
            message="Data Quality could not produce a validated response.",
        ) from exc
    except (LLMError, CircuitOpenError) as exc:
        raise APIError(
            status_code=503,
            code="data_quality_provider_error",
            message="Data Quality provider request failed.",
        ) from exc
    return result.model_copy(update={"answer": answer})


def _get_agent(request: Request) -> DataQualityAgent:
    agent: DataQualityAgent | None = request.app.state.data_quality_agent
    if agent is None:
        agent = build_data_quality_agent(request.app.state.settings)
        request.app.state.data_quality_agent = agent
    return agent
