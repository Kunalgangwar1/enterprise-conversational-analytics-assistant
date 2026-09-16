"""Feature-flag fallback policy tests."""

from app.core.feature_flags import RetrievalFeatureFlags
from app.knowledge_catalog.models import (
    KnowledgeEvidence,
    RetrievalMethod,
    RetrievalResult,
)
from app.knowledge_catalog.retriever import KnowledgeCatalogRetriever
from tests.knowledge_catalog.fakes import StubRetriever


def test_successful_hierarchy_does_not_invoke_hybrid() -> None:
    hierarchy = StubRetriever(_result(RetrievalMethod.HIERARCHICAL, sufficient=True))
    hybrid = StubRetriever(_result(RetrievalMethod.HYBRID, sufficient=True))

    result = _coordinator(hierarchy, hybrid).retrieve("claims")

    assert result.retrieval_method == RetrievalMethod.HIERARCHICAL
    assert hybrid.calls == []


def test_low_confidence_hierarchy_uses_hybrid_fallback() -> None:
    hierarchy = StubRetriever(
        RetrievalResult(
            retrieval_method=RetrievalMethod.HIERARCHICAL,
            sufficient=False,
            confidence=0.4,
        )
    )
    hybrid = StubRetriever(_result(RetrievalMethod.HYBRID, sufficient=True))

    result = _coordinator(hierarchy, hybrid).retrieve("claims")

    assert result.retrieval_method == RetrievalMethod.HYBRID
    assert hybrid.calls == ["claims"]


def test_no_hierarchy_evidence_and_vector_disabled_returns_none() -> None:
    hierarchy = StubRetriever(
        RetrievalResult(retrieval_method=RetrievalMethod.HIERARCHICAL, sufficient=False)
    )
    hybrid = StubRetriever(_result(RetrievalMethod.HYBRID, sufficient=True))
    retriever = KnowledgeCatalogRetriever(
        flags=RetrievalFeatureFlags(hierarchical_rag=True, vector_rag=False),
        hierarchical=hierarchy,
        hybrid=hybrid,
    )

    result = retriever.retrieve("unknown")

    assert result.retrieval_method == RetrievalMethod.NONE
    assert not result.evidence
    assert hybrid.calls == []


def test_hierarchy_disabled_invokes_hybrid_directly() -> None:
    hierarchy = StubRetriever(_result(RetrievalMethod.HIERARCHICAL, sufficient=True))
    hybrid = StubRetriever(_result(RetrievalMethod.HYBRID, sufficient=True))
    retriever = KnowledgeCatalogRetriever(
        flags=RetrievalFeatureFlags(hierarchical_rag=False, vector_rag=True),
        hierarchical=hierarchy,
        hybrid=hybrid,
    )

    result = retriever.retrieve("claims")

    assert result.retrieval_method == RetrievalMethod.HYBRID
    assert hierarchy.calls == []


def _coordinator(hierarchy: StubRetriever, hybrid: StubRetriever) -> KnowledgeCatalogRetriever:
    return KnowledgeCatalogRetriever(
        flags=RetrievalFeatureFlags(hierarchical_rag=True, vector_rag=True),
        hierarchical=hierarchy,
        hybrid=hybrid,
    )


def _result(method: RetrievalMethod, *, sufficient: bool) -> RetrievalResult:
    return RetrievalResult(
        evidence=(
            KnowledgeEvidence(
                evidence_id="e1",
                node_id="dataset_claims",
                title="Claims",
                section="Amounts",
                source_path="datasets/claims.md",
                text="Allowed amount is an eligible amount.",
                retrieval_method=method,
                rank=1,
            ),
        ),
        retrieval_method=method,
        sufficient=sufficient,
    )
