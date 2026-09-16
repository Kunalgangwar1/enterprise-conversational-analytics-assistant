"""Relationship-aware Semantica retrieval evaluation."""

from functools import partial
from pathlib import Path
from tempfile import TemporaryDirectory

from app.evaluation.metrics import hit_at_k, recall_at_k
from app.evaluation.models import EvaluationDataset, EvaluationSuiteResult, SemanticaCase
from app.evaluation.suites.base import SuiteContext, evaluate_cases, mean_case_metric, pass_fail
from app.evaluation.suites.fakes import (
    FixedEmbeddingClient,
    HashEmbeddingClient,
    ModelPayloadLLM,
)
from app.knowledge_catalog.context_builder import KnowledgeContextBuilder
from app.knowledge_catalog.embeddings.factory import create_embedding_client
from app.knowledge_catalog.loader import CatalogLoader
from app.knowledge_catalog.models import (
    GroundedCatalogAnswer,
    KnowledgeEvidence,
    RetrievalMethod,
)
from app.knowledge_catalog.vector_store import LanceDBKnowledgeStore
from app.llm.factory import create_llm_client
from app.semantica.agent import SemanticaAgent
from app.semantica.chunker import SemanticaChunker
from app.semantica.graph import build_adjacency, load_graph
from app.semantica.index import build_semantica_index
from app.semantica.retriever import SemanticaRetriever


class _MemoryStore:
    def __init__(self, chunks, seed_node_id: str) -> None:
        self._evidence = tuple(
            KnowledgeEvidence(
                evidence_id=chunk.chunk_id,
                chunk_id=chunk.chunk_id,
                node_id=chunk.node_id,
                title=chunk.title,
                section=chunk.section,
                source_path=chunk.source_path,
                text=chunk.text,
                retrieval_method=RetrievalMethod.SEMANTICA_GRAPH,
                rank=rank,
                score=1.0,
            )
            for rank, chunk in enumerate(chunks, start=1)
        )
        self._seed_node_id = seed_node_id

    def validate_compatibility(self, client, *, actual_dimensions=None):
        return None

    def search_hybrid(self, query, vector, *, limit):
        del query, vector
        return tuple(item for item in self._evidence if item.node_id == self._seed_node_id)[:limit]

    def all_evidence(self):
        return self._evidence


def evaluate(dataset: EvaluationDataset, context: SuiteContext) -> EvaluationSuiteResult:
    hierarchy = CatalogLoader(context.settings.knowledge_catalog_dir).load()
    chunks = SemanticaChunker(
        chunk_size_chars=context.settings.semantica_chunk_size_chars,
        overlap_chars=context.settings.semantica_chunk_overlap_chars,
    ).chunk_hierarchy(hierarchy)
    graph = build_adjacency(chunks, hierarchy)
    temporary_index: TemporaryDirectory | None = None
    shared_store: LanceDBKnowledgeStore | None = None
    shared_client_factory = None

    if context.profile.value == "integration":
        temporary_index = TemporaryDirectory(prefix="eca-eval-semantica-")
        root = Path(temporary_index.name)
        embedding_client = HashEmbeddingClient()
        build_semantica_index(
            settings=context.settings,
            embedding_client=embedding_client,
            artifact_dir=root,
        )
        shared_store = LanceDBKnowledgeStore(
            root / "lancedb",
            table_name="semantica_chunks",
            retrieval_method=RetrievalMethod.SEMANTICA_GRAPH,
            manifest_path=root / "index_manifest.json",
        )

        def integration_client_factory():
            return embedding_client

        shared_client_factory = integration_client_factory
        graph = load_graph(
            root / "adjacency.json",
            chunk_ids={item.evidence_id for item in shared_store.all_evidence()},
        )
    elif context.profile.value == "live":
        root = context.settings.artifacts_output_dir / "semantica"
        shared_store = LanceDBKnowledgeStore(
            root / "lancedb",
            table_name="semantica_chunks",
            retrieval_method=RetrievalMethod.SEMANTICA_GRAPH,
            manifest_path=root / "index_manifest.json",
        )
        shared_client_factory = partial(create_embedding_client, context.settings)
        graph = load_graph(
            root / "adjacency.json",
            chunk_ids={item.evidence_id for item in shared_store.all_evidence()},
        )

    def one(raw_case):
        case = SemanticaCase.model_validate(raw_case)
        retriever = SemanticaRetriever(
            store=shared_store or _MemoryStore(chunks, case.seed_node_id),
            graph=graph,
            embedding_client_factory=shared_client_factory or FixedEmbeddingClient,
            seed_top_k=context.settings.semantica_seed_top_k,
            max_hops=context.settings.semantica_max_hops,
            max_evidence=context.settings.semantica_max_evidence,
        )
        result = retriever.retrieve(case.question)
        actual_nodes = [item.node_id for item in result.evidence]
        distances = [item.graph_distance or 0 for item in result.evidence]
        expected = case.expected_evidence_ids or case.acceptable_evidence_ids
        hit = hit_at_k(actual_nodes, expected, case.k)
        recall = (
            hit if case.acceptable_evidence_ids else recall_at_k(actual_nodes, expected, case.k)
        )
        invalid = sum(value > context.settings.semantica_max_hops for value in distances)
        graph_hit = float(any(value > 0 for value in distances))
        seed_hit = float(case.seed_node_id in actual_nodes)
        if result.evidence:
            cited_id = result.evidence[0].evidence_id
            llm_factory = (
                partial(create_llm_client, context.settings)
                if context.profile.value == "live"
                else lambda: ModelPayloadLLM(
                    {
                        GroundedCatalogAnswer: {
                            "answer": "The graph-expanded synthetic evidence supports this answer.",
                            "citation_ids": [cited_id],
                        }
                    }
                )
            )
        else:
            llm_factory = partial(create_llm_client, context.settings)
        answer = SemanticaAgent(
            retriever=retriever,
            context_builder=KnowledgeContextBuilder(
                max_chars=context.settings.knowledge_context_max_chars
            ),
            llm_client_factory=llm_factory,
        ).answer(case.question)
        supplied_ids = {item.evidence_id for item in result.evidence}
        invalid_citations = len({item.id for item in answer.citations} - supplied_ids)
        return pass_fail(
            case,
            bool(hit) and invalid == 0 and invalid_citations == 0,
            metrics={
                "seed_hit": seed_hit,
                "recall_at_k": recall,
                "graph_supported_hit": graph_hit,
                "max_graph_distance": float(max(distances, default=0)),
                "invalid_distance": float(invalid),
                "invalid_citations": float(invalid_citations),
            },
            expected=", ".join(expected),
            actual=", ".join(dict.fromkeys(actual_nodes)),
        )

    try:
        return evaluate_cases(
            dataset,
            one,
            lambda items: {
                "seed_hit_rate": mean_case_metric(items, "seed_hit"),
                "evidence_recall_at_k": mean_case_metric(items, "recall_at_k"),
                "graph_supported_hit_rate": mean_case_metric(items, "graph_supported_hit"),
                "max_graph_distance_observed": max(
                    (item.metrics.get("max_graph_distance", 0) for item in items), default=0
                ),
                "invalid_distance_count": sum(
                    item.metrics.get("invalid_distance", 0) for item in items
                ),
                "invalid_citation_count": sum(
                    item.metrics.get("invalid_citations", 0) for item in items
                ),
            },
        )
    finally:
        if temporary_index is not None:
            temporary_index.cleanup()
