"""Request-scoped API boundary for the Knowledge Catalog specialist."""

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict

from app.api.errors import APIError, APIErrorResponse
from app.auth.dependencies import CurrentPrincipal, require_permission
from app.auth.permissions import Permission
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
from app.security.rate_limit import enforce_rate_limit
from app.security.request_limits import UserQuestion

router = APIRouter(
    prefix="/knowledge-catalog",
    tags=["knowledge-catalog"],
    dependencies=[Depends(require_permission(Permission.KNOWLEDGE_CATALOG_READ))],
)


class KnowledgeCatalogQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: UserQuestion


@router.post(
    "/query",
    response_model=KnowledgeCatalogResult,
    responses={
        429: {"model": APIErrorResponse},
        500: {"model": APIErrorResponse},
        503: {"model": APIErrorResponse},
    },
)
def query_knowledge_catalog(
    payload: KnowledgeCatalogQuery,
    request: Request,
    principal: CurrentPrincipal,
) -> KnowledgeCatalogResult:
    """Protect the question, invoke the specialist, then restore current tokens."""

    enforce_rate_limit(request, principal, "knowledge_catalog")
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
