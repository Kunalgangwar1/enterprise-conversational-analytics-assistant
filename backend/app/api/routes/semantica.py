"""Thin privacy and error boundary for Semantica retrieval."""

from typing import Annotated

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, StringConstraints

from app.api.errors import APIError, APIErrorResponse
from app.knowledge_catalog.exceptions import EmbeddingError, KnowledgeIndexError
from app.knowledge_catalog.models import KnowledgeCatalogResult
from app.llm.exceptions import LLMError
from app.privacy import PrivacyProcessor, ResponseUnmasker
from app.semantica.agent import SemanticaAgent
from app.semantica.exceptions import SemanticaError
from app.semantica.factory import build_semantica_agent

router = APIRouter(prefix="/semantica", tags=["semantica"])


class SemanticaQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4_000)
    ]


@router.post(
    "/query",
    response_model=KnowledgeCatalogResult,
    responses={500: {"model": APIErrorResponse}, 503: {"model": APIErrorResponse}},
)
def query_semantica(payload: SemanticaQuery, request: Request) -> KnowledgeCatalogResult:
    privacy = PrivacyProcessor().process(payload.question)
    try:
        result = _get_agent(request).answer(privacy.safe_text)
        answer = ResponseUnmasker().unmask(result.answer, privacy.token_mappings)
    except SemanticaError as exc:
        raise APIError(
            status_code=500,
            code="semantica_invalid_response",
            message="Semantica could not produce a validated response.",
        ) from exc
    except (EmbeddingError, KnowledgeIndexError, LLMError) as exc:
        raise APIError(
            status_code=503,
            code="semantica_unavailable",
            message="Semantica retrieval is not currently available.",
        ) from exc
    return result.model_copy(update={"answer": answer})


def _get_agent(request: Request) -> SemanticaAgent:
    agent: SemanticaAgent | None = request.app.state.semantica_agent
    if agent is None:
        agent = build_semantica_agent(request.app.state.settings)
        request.app.state.semantica_agent = agent
    return agent
