"""Feature-flagged orchestration of primary and fallback retrieval paths."""

from typing import Protocol

from app.core.feature_flags import RetrievalFeatureFlags
from app.knowledge_catalog.models import RetrievalMethod, RetrievalResult
from app.llm.exceptions import LLMError


class CatalogRetrievalStrategy(Protocol):
    def retrieve(self, safe_question: str) -> RetrievalResult: ...


class KnowledgeCatalogRetriever:
    """Prefer hierarchy and use hybrid retrieval only on an explicit fallback path."""

    def __init__(
        self,
        *,
        flags: RetrievalFeatureFlags,
        hierarchical: CatalogRetrievalStrategy,
        hybrid: CatalogRetrievalStrategy,
    ) -> None:
        self._flags = flags
        self._hierarchical = hierarchical
        self._hybrid = hybrid

    def retrieve(self, safe_question: str) -> RetrievalResult:
        if self._flags.hierarchical_rag:
            try:
                hierarchy_result = self._hierarchical.retrieve(safe_question)
            except LLMError:
                if self._flags.vector_rag:
                    return self._hybrid.retrieve(safe_question)
                raise
            if hierarchy_result.sufficient and hierarchy_result.evidence:
                return hierarchy_result
        if self._flags.vector_rag:
            return self._hybrid.retrieve(safe_question)
        return RetrievalResult(
            retrieval_method=RetrievalMethod.NONE,
            sufficient=False,
        )
