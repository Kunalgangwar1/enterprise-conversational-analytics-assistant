"""End-to-end local Knowledge Catalog retrieval without Azure dependencies."""

from pathlib import Path

import pytest

from app.core.config import Settings
from app.core.feature_flags import RetrievalFeatureFlags
from app.knowledge_catalog.agent import KnowledgeCatalogAgent
from app.knowledge_catalog.context_builder import KnowledgeContextBuilder
from app.knowledge_catalog.hierarchy import HierarchicalCatalogRetriever
from app.knowledge_catalog.hybrid_retriever import HybridCatalogRetriever
from app.knowledge_catalog.index import build_index
from app.knowledge_catalog.loader import CatalogLoader
from app.knowledge_catalog.models import RetrievalMethod
from app.knowledge_catalog.retriever import KnowledgeCatalogRetriever
from app.knowledge_catalog.vector_store import LanceDBKnowledgeStore
from tests.knowledge_catalog.fakes import FakeEmbeddingClient
from tests.llm.fakes import FakeLLMClient

pytestmark = pytest.mark.integration


def test_real_corpus_hierarchy_hybrid_and_grounded_answer(tmp_path: Path) -> None:
    catalog_root = Path(__file__).resolve().parents[2] / "data" / "knowledge_catalog"
    settings = Settings(
        app_env="test",
        knowledge_catalog_dir=catalog_root,
        artifacts_output_dir=tmp_path / "artifacts",
    )
    fake_embeddings = FakeEmbeddingClient()
    index_dir = tmp_path / "catalog-index" / "lancedb"
    manifest = build_index(
        settings=settings,
        embedding_client=fake_embeddings,
        index_dir=index_dir,
    )
    hierarchy = CatalogLoader(catalog_root).load()

    hierarchy_llm = FakeLLMClient(
        structured_payloads=[
            {"selected_child_ids": ["domain_claims"], "confidence": 0.95},
            {"selected_child_ids": ["dataset_claims"], "confidence": 0.92},
        ]
    )
    hierarchical = HierarchicalCatalogRetriever(
        hierarchy=hierarchy,
        llm_client_factory=lambda: hierarchy_llm,
        max_depth=4,
        max_branches=3,
        min_confidence=0.60,
        top_k=6,
    )
    hybrid = HybridCatalogRetriever(
        store=LanceDBKnowledgeStore(index_dir),
        embedding_client_factory=lambda: fake_embeddings,
        top_k=6,
    )
    primary = KnowledgeCatalogRetriever(
        flags=RetrievalFeatureFlags(hierarchical_rag=True, vector_rag=True),
        hierarchical=hierarchical,
        hybrid=hybrid,
    ).retrieve("What does allowed amount mean for a claim?")

    assert manifest.chunk_count > 0
    assert primary.retrieval_method == RetrievalMethod.HIERARCHICAL
    assert primary.evidence[0].node_id == "dataset_claims"

    fallback_retriever = KnowledgeCatalogRetriever(
        flags=RetrievalFeatureFlags(hierarchical_rag=False, vector_rag=True),
        hierarchical=hierarchical,
        hybrid=hybrid,
    )
    fallback = fallback_retriever.retrieve("What does allowed amount mean for a claim?")
    assert fallback.retrieval_method == RetrievalMethod.HYBRID
    assert any(item.node_id == "dataset_claims" for item in fallback.evidence)

    cited_id = fallback.evidence[0].evidence_id
    answer_llm = FakeLLMClient(
        structured_payload={
            "answer": "The catalog describes allowed amount as an eligible claim amount.",
            "citation_ids": [cited_id],
        }
    )
    result = KnowledgeCatalogAgent(
        retriever=fallback_retriever,
        context_builder=KnowledgeContextBuilder(max_chars=4_000),
        llm_client_factory=lambda: answer_llm,
    ).answer("What does allowed amount mean for a claim?")

    assert result.retrieval_method == RetrievalMethod.HYBRID
    assert result.citations[0].id == cited_id
    assert (catalog_root / result.citations[0].source_path).is_file()
