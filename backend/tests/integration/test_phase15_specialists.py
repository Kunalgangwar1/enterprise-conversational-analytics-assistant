"""End-to-end Phase 15 specialists using real content and fake providers."""

from pathlib import Path

import pytest

from app.core.config import Settings
from app.data_discovery.factory import build_data_discovery_service
from app.data_quality.agent import DataQualityAgent
from app.data_quality.context_builder import DataQualityContextBuilder
from app.data_quality.loader import DataQualityLoader
from app.data_quality.retriever import DataQualityRetriever
from app.knowledge_catalog.context_builder import KnowledgeContextBuilder
from app.knowledge_catalog.models import RetrievalMethod
from app.knowledge_catalog.vector_store import LanceDBKnowledgeStore
from app.semantica.agent import SemanticaAgent
from app.semantica.graph import load_graph
from app.semantica.index import build_semantica_index
from app.semantica.retriever import SemanticaRetriever
from tests.knowledge_catalog.fakes import FakeEmbeddingClient
from tests.llm.fakes import FakeLLMClient

pytestmark = pytest.mark.integration


def test_phase15_specialists_with_real_metadata_and_corpora(tmp_path: Path) -> None:
    backend_root = Path(__file__).resolve().parents[2]
    settings = Settings(
        _env_file=None,
        app_env="test",
        knowledge_catalog_dir=backend_root / "data" / "knowledge_catalog",
        data_quality_dir=backend_root / "data" / "data_quality",
        artifacts_output_dir=tmp_path / "artifacts",
    )

    discovery = build_data_discovery_service(settings).search(
        "Which dataset contains provider specialty?"
    )
    assert discovery.matches[0].table == "providers"

    dq_fake = FakeLLMClient(
        structured_payload={
            "answer": "Claims amounts follow non-negative and ordering expectations.",
            "citation_ids": ["dq_rules_claims"],
        }
    )
    dq_result = DataQualityAgent(
        retriever=DataQualityRetriever(
            DataQualityLoader(settings.data_quality_dir).load(),
            top_k=5,
        ),
        context_builder=DataQualityContextBuilder(max_chars=4_000),
        llm_client_factory=lambda: dq_fake,
    ).answer("What quality rules apply to claims amounts?")
    assert dq_result.citations[0].id == "dq_rules_claims"

    fake_embeddings = FakeEmbeddingClient()
    semantica_root = tmp_path / "semantica"
    manifest, edge_count = build_semantica_index(
        settings=settings,
        embedding_client=fake_embeddings,
        artifact_dir=semantica_root,
    )
    store = LanceDBKnowledgeStore(
        semantica_root / "lancedb",
        table_name="semantica_chunks",
        retrieval_method=RetrievalMethod.SEMANTICA_GRAPH,
        manifest_path=semantica_root / "index_manifest.json",
    )
    graph = load_graph(
        semantica_root / "adjacency.json",
        chunk_ids={item.evidence_id for item in store.all_evidence()},
    )
    retriever = SemanticaRetriever(
        store=store,
        graph=graph,
        embedding_client_factory=lambda: fake_embeddings,
        seed_top_k=1,
        max_hops=2,
        max_evidence=12,
    )
    semantica_question = "Use Semantica to explain how claims relate to providers."
    evidence = retriever.retrieve(semantica_question)
    assert manifest.chunk_count > 0 and edge_count > 0
    assert max(item.graph_distance or 0 for item in evidence.evidence) <= 2

    cited_id = evidence.evidence[0].evidence_id
    semantica_fake = FakeLLMClient(
        structured_payload={
            "answer": "Claims have documented participant relationships.",
            "citation_ids": [cited_id],
        }
    )
    result = SemanticaAgent(
        retriever=retriever,
        context_builder=KnowledgeContextBuilder(max_chars=6_000),
        llm_client_factory=lambda: semantica_fake,
    ).answer(semantica_question)

    assert result.retrieval_method == RetrievalMethod.SEMANTICA_GRAPH
    assert result.citations[0].id == cited_id
    assert (settings.knowledge_catalog_dir / result.citations[0].source_path).is_file()
