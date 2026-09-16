"""Embedding-backed hybrid fallback over the local LanceDB index."""

from collections.abc import Callable

from app.knowledge_catalog.embeddings.base import EmbeddingClient
from app.knowledge_catalog.models import RetrievalMethod, RetrievalResult
from app.knowledge_catalog.vector_store import LanceDBKnowledgeStore


class HybridCatalogRetriever:
    """Run LanceDB vector plus BM25 search with native RRF fusion."""

    def __init__(
        self,
        *,
        store: LanceDBKnowledgeStore,
        embedding_client_factory: Callable[[], EmbeddingClient],
        top_k: int,
    ) -> None:
        self._store = store
        self._embedding_client_factory = embedding_client_factory
        self._top_k = top_k

    def retrieve(self, safe_question: str) -> RetrievalResult:
        client = self._embedding_client_factory()
        self._store.validate_compatibility(client)
        query_vector = client.embed_query(safe_question)
        self._store.validate_compatibility(client, actual_dimensions=len(query_vector))
        evidence = self._store.search_hybrid(safe_question, query_vector, limit=self._top_k)
        return RetrievalResult(
            evidence=evidence,
            retrieval_method=RetrievalMethod.HYBRID,
            sufficient=bool(evidence),
        )
