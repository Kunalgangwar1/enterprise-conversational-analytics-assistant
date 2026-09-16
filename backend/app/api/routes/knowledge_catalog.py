"""Request-scoped API boundary for the Knowledge Catalog specialist."""

from typing import Annotated

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, StringConstraints

from app.api.errors import APIError, APIErrorResponse
from app.knowledge_catalog.agent import KnowledgeCatalogAgent
from app.knowledge_catalog.exceptions import (
    CatalogHierarchyError,
    CatalogLoadError,
    CatalogTraversalError,
    CitationValidationError,
    EmbeddingConfigurationError,
    EmbeddingError,
    KnowledgeIndexError,
)
from app.knowledge_catalog.factory import build_knowledge_catalog_agent
from app.knowledge_catalog.models import KnowledgeCatalogResult
from app.llm.exceptions import LLMError
from app.privacy import PrivacyProcessor, ResponseUnmasker

router = APIRouter(prefix="/knowledge-catalog", tags=["knowledge-catalog"])


class KnowledgeCatalogQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4_000)
    ]


@router.post(
    "/query",
    response_model=KnowledgeCatalogResult,
    responses={500: {"model": APIErrorResponse}, 503: {"model": APIErrorResponse}},
)
def query_knowledge_catalog(
    payload: KnowledgeCatalogQuery,
    request: Request,
) -> KnowledgeCatalogResult:
    """Protect the question, invoke the specialist, then restore current tokens."""

    privacy_result = PrivacyProcessor().process(payload.question)
    try:
        result = _get_agent(request).answer(privacy_result.safe_text)
        answer = ResponseUnmasker().unmask(result.answer, privacy_result.token_mappings)
    except (EmbeddingConfigurationError, CatalogLoadError, KnowledgeIndexError) as exc:
        raise APIError(
            status_code=503,
            code="knowledge_catalog_unavailable",
            message="Knowledge Catalog retrieval is not currently available.",
        ) from exc
    except (CatalogHierarchyError, CatalogTraversalError, CitationValidationError) as exc:
        raise APIError(
            status_code=500,
            code="knowledge_catalog_invalid_response",
            message="Knowledge Catalog could not produce a validated response.",
        ) from exc
    except (EmbeddingError, LLMError) as exc:
        raise APIError(
            status_code=503,
            code="knowledge_catalog_provider_error",
            message="Knowledge Catalog provider request failed.",
        ) from exc
    return result.model_copy(update={"answer": answer})


def _get_agent(request: Request) -> KnowledgeCatalogAgent:
    agent: KnowledgeCatalogAgent | None = request.app.state.knowledge_catalog_agent
    if agent is None:
        agent = build_knowledge_catalog_agent(request.app.state.settings)
        request.app.state.knowledge_catalog_agent = agent
    return agent
