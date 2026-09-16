"""Hybrid seed retrieval followed by bounded deterministic graph expansion."""

from collections.abc import Callable

from app.knowledge_catalog.embeddings.base import EmbeddingClient
from app.knowledge_catalog.models import KnowledgeEvidence, RetrievalMethod, RetrievalResult
from app.knowledge_catalog.vector_store import LanceDBKnowledgeStore
from app.semantica.models import SemanticaGraph


class SemanticaRetriever:
    def __init__(
        self,
        *,
        store: LanceDBKnowledgeStore,
        graph: SemanticaGraph,
        embedding_client_factory: Callable[[], EmbeddingClient],
        seed_top_k: int,
        max_hops: int,
        max_evidence: int,
    ) -> None:
        if not 0 <= max_hops <= 2:
            raise ValueError("Semantica max_hops must be between zero and two")
        self._store = store
        self._graph = graph
        self._embedding_client_factory = embedding_client_factory
        self._seed_top_k = seed_top_k
        self._max_hops = max_hops
        self._max_evidence = max_evidence

    def retrieve(self, safe_question: str) -> RetrievalResult:
        client = self._embedding_client_factory()
        self._store.validate_compatibility(client)
        vector = client.embed_query(safe_question)
        self._store.validate_compatibility(client, actual_dimensions=len(vector))
        seeds = self._store.search_hybrid(safe_question, vector, limit=self._seed_top_k)
        if not seeds:
            return RetrievalResult(
                retrieval_method=RetrievalMethod.SEMANTICA_GRAPH,
                sufficient=False,
            )
        indexed = {item.evidence_id: item for item in self._store.all_evidence()}
        result: list[KnowledgeEvidence] = []
        visited: set[str] = set()
        frontier: list[tuple[str, int]] = []
        for seed in seeds:
            if seed.evidence_id in visited or len(result) >= self._max_evidence:
                continue
            visited.add(seed.evidence_id)
            seed_rank = seed.rank
            result.append(
                seed.model_copy(
                    update={
                        "retrieval_method": RetrievalMethod.SEMANTICA_GRAPH,
                        "graph_distance": 0,
                        "seed_rank": seed_rank,
                        "rank": len(result) + 1,
                    }
                )
            )
            frontier.append((seed.evidence_id, seed_rank))

        for distance in range(1, self._max_hops + 1):
            candidates: dict[str, int] = {}
            for node_id, seed_rank in sorted(frontier, key=lambda item: (item[1], item[0])):
                for neighbor in self._graph.adjacency.get(node_id, ()):
                    if neighbor not in visited and neighbor in indexed:
                        candidates[neighbor] = min(candidates.get(neighbor, seed_rank), seed_rank)
            frontier = []
            for node_id, seed_rank in sorted(
                candidates.items(), key=lambda item: (item[1], item[0])
            ):
                if len(result) >= self._max_evidence:
                    break
                visited.add(node_id)
                result.append(
                    indexed[node_id].model_copy(
                        update={
                            "retrieval_method": RetrievalMethod.SEMANTICA_GRAPH,
                            "graph_distance": distance,
                            "seed_rank": seed_rank,
                            "rank": len(result) + 1,
                            "score": None,
                        }
                    )
                )
                frontier.append((node_id, seed_rank))
            if not frontier or len(result) >= self._max_evidence:
                break
        return RetrievalResult(
            evidence=tuple(result),
            retrieval_method=RetrievalMethod.SEMANTICA_GRAPH,
            sufficient=bool(result),
        )
