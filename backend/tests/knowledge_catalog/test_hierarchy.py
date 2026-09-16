"""Bounded hierarchical retrieval tests."""

import pytest

from app.knowledge_catalog.exceptions import CatalogTraversalError
from app.knowledge_catalog.hierarchy import HierarchicalCatalogRetriever
from app.knowledge_catalog.loader import CatalogHierarchy
from app.knowledge_catalog.models import RetrievalMethod
from tests.llm.fakes import FakeLLMClient


@pytest.mark.parametrize(
    ("question", "payloads", "expected"),
    [
        (
            "What does allowed amount mean?",
            [
                {"selected_child_ids": ["domain_claims"], "confidence": 0.95},
                {"selected_child_ids": ["dataset_claims"], "confidence": 0.91},
            ],
            "dataset_claims",
        ),
        (
            "Which table stores no-show appointments?",
            [
                {"selected_child_ids": ["domain_scheduling"], "confidence": 0.94},
                {"selected_child_ids": ["dataset_appointments"], "confidence": 0.90},
            ],
            "dataset_appointments",
        ),
        (
            "How should sensitive fields be handled?",
            [{"selected_child_ids": ["policy_sensitive_data"], "confidence": 0.96}],
            "policy_sensitive_data",
        ),
    ],
)
def test_hierarchy_selects_relevant_branch(
    hierarchy: CatalogHierarchy,
    question: str,
    payloads: list[dict[str, object]],
    expected: str,
) -> None:
    result = _retriever(hierarchy, FakeLLMClient(structured_payloads=payloads)).retrieve(question)

    assert result.sufficient is True
    assert result.retrieval_method == RetrievalMethod.HIERARCHICAL
    assert result.evidence[0].node_id == expected


def test_invalid_llm_child_id_is_rejected(hierarchy: CatalogHierarchy) -> None:
    retriever = _retriever(
        hierarchy,
        FakeLLMClient(
            structured_payload={"selected_child_ids": ["not_a_node"], "confidence": 0.99}
        ),
    )

    with pytest.raises(CatalogTraversalError, match="unknown child"):
        retriever.retrieve("claims")


def test_low_confidence_returns_controlled_insufficient_result(hierarchy: CatalogHierarchy) -> None:
    result = _retriever(
        hierarchy,
        FakeLLMClient(
            structured_payload={"selected_child_ids": ["domain_claims"], "confidence": 0.40}
        ),
    ).retrieve("claims")

    assert result.sufficient is False
    assert result.confidence == 0.40


def test_max_depth_is_enforced(hierarchy: CatalogHierarchy) -> None:
    result = _retriever(
        hierarchy,
        FakeLLMClient(
            structured_payload={"selected_child_ids": ["domain_claims"], "confidence": 0.90}
        ),
        max_depth=1,
    ).retrieve("claims")

    assert result.sufficient is False


def test_max_branches_is_enforced(hierarchy: CatalogHierarchy) -> None:
    fake = FakeLLMClient(
        structured_payload={
            "selected_child_ids": [
                "policy_data_access",
                "policy_data_retention",
                "policy_sensitive_data",
                "domain_claims",
            ],
            "confidence": 0.90,
        }
    )
    result = _retriever(hierarchy, fake, max_branches=3).retrieve("policies")

    assert len(result.evidence) == 3


def _retriever(
    hierarchy: CatalogHierarchy,
    fake: FakeLLMClient,
    *,
    max_depth: int = 4,
    max_branches: int = 3,
) -> HierarchicalCatalogRetriever:
    return HierarchicalCatalogRetriever(
        hierarchy=hierarchy,
        llm_client_factory=lambda: fake,
        max_depth=max_depth,
        max_branches=max_branches,
        min_confidence=0.60,
        top_k=6,
    )
