"""Bounded graph expansion and temporary LanceDB seed tests."""

from pathlib import Path

from app.core.config import Settings
from app.knowledge_catalog.models import KnowledgeEvidence, RetrievalMethod
from app.knowledge_catalog.vector_store import LanceDBKnowledgeStore
from app.semantica.graph import load_graph
from app.semantica.index import build_semantica_index
from app.semantica.models import SemanticaGraph
from app.semantica.retriever import SemanticaRetriever
from tests.knowledge_catalog.fakes import FakeEmbeddingClient


def test_controlled_chain_expands_only_two_hops_without_duplicates() -> None:
    evidence = tuple(_evidence(node_id) for node_id in ("a", "b", "c", "d", "unrelated"))
    store = _StubStore(seed=evidence[0], all_evidence=evidence)
    graph = SemanticaGraph(
        adjacency={
            "a": ("b",),
            "b": ("a", "c"),
            "c": ("b", "d"),
            "d": ("c",),
            "unrelated": (),
        }
    )
    retriever = SemanticaRetriever(
        store=store,  # type: ignore[arg-type]
        graph=graph,
        embedding_client_factory=FakeEmbeddingClient,
        seed_top_k=1,
        max_hops=2,
        max_evidence=12,
    )

    result = retriever.retrieve("claims")

    assert [item.evidence_id for item in result.evidence] == ["a", "b", "c"]
    assert [item.graph_distance for item in result.evidence] == [0, 1, 2]
    assert "d" not in {item.evidence_id for item in result.evidence}
    assert "unrelated" not in {item.evidence_id for item in result.evidence}


def test_max_evidence_and_deterministic_order_are_enforced() -> None:
    evidence = tuple(_evidence(node_id) for node_id in ("a", "b", "c", "d"))
    graph = SemanticaGraph(adjacency={"a": ("b", "c", "d"), "b": ("a",), "c": ("a",), "d": ("a",)})
    store = _StubStore(seed=evidence[0], all_evidence=evidence)
    retriever = SemanticaRetriever(
        store=store,  # type: ignore[arg-type]
        graph=graph,
        embedding_client_factory=FakeEmbeddingClient,
        seed_top_k=1,
        max_hops=2,
        max_evidence=2,
    )

    first = retriever.retrieve("claims")
    second = retriever.retrieve("claims")

    assert len(first.evidence) == 2
    assert first == second


def test_real_temporary_lancedb_seed_and_adjacency_build(
    catalog_root: Path,
    tmp_path: Path,
) -> None:
    settings = Settings(
        _env_file=None,
        knowledge_catalog_dir=catalog_root,
        artifacts_output_dir=tmp_path / "unused",
    )
    client = FakeEmbeddingClient()
    artifact_dir = tmp_path / "semantica"
    manifest, edges = build_semantica_index(
        settings=settings,
        embedding_client=client,
        artifact_dir=artifact_dir,
    )
    store = LanceDBKnowledgeStore(
        artifact_dir / "lancedb",
        table_name="semantica_chunks",
        retrieval_method=RetrievalMethod.SEMANTICA_GRAPH,
        manifest_path=artifact_dir / "index_manifest.json",
    )
    graph = load_graph(
        artifact_dir / "adjacency.json",
        chunk_ids={item.evidence_id for item in store.all_evidence()},
    )
    result = SemanticaRetriever(
        store=store,
        graph=graph,
        embedding_client_factory=lambda: client,
        seed_top_k=1,
        max_hops=2,
        max_evidence=8,
    ).retrieve("claim allowed_amount provider relationship")

    assert manifest.chunk_count == store.count()
    assert edges > 0
    assert result.evidence
    assert result.evidence[0].graph_distance == 0
    assert max(item.graph_distance or 0 for item in result.evidence) <= 2
    assert len(result.evidence) <= 8


def _evidence(node_id: str) -> KnowledgeEvidence:
    return KnowledgeEvidence(
        evidence_id=node_id,
        chunk_id=node_id,
        node_id=node_id,
        title=node_id.title(),
        section="Section",
        source_path=f"datasets/{node_id}.md",
        text=f"Evidence {node_id}",
        retrieval_method=RetrievalMethod.SEMANTICA_GRAPH,
        rank=1,
    )


class _StubStore:
    def __init__(
        self,
        *,
        seed: KnowledgeEvidence,
        all_evidence: tuple[KnowledgeEvidence, ...],
    ) -> None:
        self._seed = seed
        self._all = all_evidence

    def validate_compatibility(self, *_args: object, **_kwargs: object) -> None:
        return None

    def search_hybrid(self, *_args: object, **_kwargs: object) -> tuple[KnowledgeEvidence, ...]:
        return (self._seed,)

    def all_evidence(self) -> tuple[KnowledgeEvidence, ...]:
        return self._all
