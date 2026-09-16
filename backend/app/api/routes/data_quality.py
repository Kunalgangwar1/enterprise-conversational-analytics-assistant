"""Thin privacy and error boundary for Data Quality guidance."""

from typing import Annotated

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, StringConstraints

from app.api.errors import APIError, APIErrorResponse
from app.data_quality.agent import DataQualityAgent
from app.data_quality.exceptions import DataQualityError
from app.data_quality.factory import build_data_quality_agent
from app.data_quality.models import DataQualityResult
from app.llm.exceptions import LLMError
from app.privacy import PrivacyProcessor, ResponseUnmasker

router = APIRouter(prefix="/data-quality", tags=["data-quality"])


class DataQualityQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4_000)
    ]


@router.post(
    "/query",
    response_model=DataQualityResult,
    responses={500: {"model": APIErrorResponse}, 503: {"model": APIErrorResponse}},
)
def query_data_quality(payload: DataQualityQuery, request: Request) -> DataQualityResult:
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
    except LLMError as exc:
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
