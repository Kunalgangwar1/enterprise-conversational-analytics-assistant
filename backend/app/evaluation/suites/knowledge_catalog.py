"""Knowledge Catalog retrieval, answer grounding, and citation evaluation."""

from functools import partial
from pathlib import Path
from tempfile import TemporaryDirectory

from app.evaluation.metrics import hit_at_k, recall_at_k, reciprocal_rank
from app.evaluation.models import EvaluationDataset, EvaluationSuiteResult, RetrievalCase
from app.evaluation.suites.base import SuiteContext, evaluate_cases, mean_case_metric, pass_fail
from app.evaluation.suites.fakes import HashEmbeddingClient, ModelPayloadLLM
from app.knowledge_catalog.agent import KnowledgeCatalogAgent
from app.knowledge_catalog.context_builder import KnowledgeContextBuilder
from app.knowledge_catalog.embeddings.factory import create_embedding_client
from app.knowledge_catalog.hierarchy import HierarchicalCatalogRetriever
from app.knowledge_catalog.hybrid_retriever import HybridCatalogRetriever
from app.knowledge_catalog.index import build_index
from app.knowledge_catalog.loader import CatalogHierarchy, CatalogLoader
from app.knowledge_catalog.models import (
    CatalogTraversalDecision,
    GroundedCatalogAnswer,
    RetrievalResult,
)
from app.knowledge_catalog.vector_store import LanceDBKnowledgeStore
from app.llm.factory import create_llm_client


class _FixedRetriever:
    def __init__(self, result: RetrievalResult) -> None:
        self._result = result

    def retrieve(self, safe_question: str) -> RetrievalResult:
        del safe_question
        return self._result


def evaluate(dataset: EvaluationDataset, context: SuiteContext) -> EvaluationSuiteResult:
    hierarchy = CatalogLoader(context.settings.knowledge_catalog_dir).load()
    temporary_index: TemporaryDirectory | None = None
    hybrid: HybridCatalogRetriever | None = None

    if context.profile.value == "integration":
        temporary_index = TemporaryDirectory(prefix="eca-eval-catalog-")
        index_dir = Path(temporary_index.name) / "lancedb"
        embedding_client = HashEmbeddingClient()
        build_index(
            settings=context.settings,
            embedding_client=embedding_client,
            index_dir=index_dir,
        )
        hybrid = HybridCatalogRetriever(
            store=LanceDBKnowledgeStore(index_dir),
            embedding_client_factory=lambda: embedding_client,
            top_k=context.settings.knowledge_catalog_top_k,
        )
    elif context.profile.value == "live":
        hybrid = HybridCatalogRetriever(
            store=LanceDBKnowledgeStore(
                context.settings.artifacts_output_dir / "knowledge_catalog" / "lancedb"
            ),
            embedding_client_factory=partial(create_embedding_client, context.settings),
            top_k=context.settings.knowledge_catalog_top_k,
        )

    def one(raw_case):
        case = RetrievalCase.model_validate(raw_case)
        expected = case.expected_evidence_ids or case.acceptable_evidence_ids
        if hybrid is not None and not (
            context.profile.value == "integration" and case.expect_no_evidence
        ):
            retrieval = hybrid.retrieve(case.question)
        else:
            retrieval = _offline_retrieve(case, hierarchy, context)
        actual = [item.node_id for item in retrieval.evidence]
        no_evidence_correct = float(case.expect_no_evidence and not actual)
        hit = no_evidence_correct or hit_at_k(actual, expected, case.k)
        recall = (
            1.0
            if (case.expect_no_evidence and not actual) or (case.acceptable_evidence_ids and hit)
            else recall_at_k(actual, expected, case.k)
        )
        mrr = 1.0 if case.expect_no_evidence and not actual else reciprocal_rank(actual, expected)
        if retrieval.evidence:
            cited_id = retrieval.evidence[0].evidence_id
            llm_factory = (
                partial(create_llm_client, context.settings)
                if context.profile.value == "live"
                else lambda: ModelPayloadLLM(
                    {
                        GroundedCatalogAnswer: {
                            "answer": (
                                "The supplied synthetic catalog evidence supports this answer."
                            ),
                            "citation_ids": [cited_id],
                        }
                    }
                )
            )
        else:
            llm_factory = partial(create_llm_client, context.settings)
        answer = KnowledgeCatalogAgent(
            retriever=_FixedRetriever(retrieval),
            context_builder=KnowledgeContextBuilder(
                max_chars=context.settings.knowledge_context_max_chars
            ),
            llm_client_factory=llm_factory,
        ).answer(case.question)
        supplied = {item.evidence_id for item in retrieval.evidence}
        invalid_citations = len({item.id for item in answer.citations} - supplied)
        case_metrics = {
            "hit": float(hit),
            "recall_at_k": recall,
            "mrr": mrr,
            "citation_valid": float(invalid_citations == 0),
            "invalid_citations": float(invalid_citations),
        }
        if case.expect_no_evidence:
            case_metrics["no_evidence_correct"] = no_evidence_correct
        return pass_fail(
            case,
            bool(hit) and invalid_citations == 0,
            metrics=case_metrics,
            expected=", ".join(expected) or "no evidence",
            actual=", ".join(dict.fromkeys(actual)) or "no evidence",
        )

    try:
        return evaluate_cases(
            dataset,
            one,
            lambda items: {
                "retrieval_hit_rate": mean_case_metric(items, "hit"),
                "recall_at_k": mean_case_metric(items, "recall_at_k"),
                "mrr": mean_case_metric(items, "mrr"),
                "citation_validity_rate": mean_case_metric(items, "citation_valid"),
                "no_evidence_accuracy": mean_case_metric(items, "no_evidence_correct"),
                "invalid_citation_count": sum(
                    item.metrics.get("invalid_citations", 0) for item in items
                ),
            },
        )
    finally:
        if temporary_index is not None:
            temporary_index.cleanup()


def _offline_retrieve(
    case: RetrievalCase,
    hierarchy: CatalogHierarchy,
    context: SuiteContext,
) -> RetrievalResult:
    expected = case.expected_evidence_ids or case.acceptable_evidence_ids
    if case.expect_no_evidence:
        decisions = [{"selected_child_ids": [], "confidence": 0.1}]
    else:
        decisions = [
            {"selected_child_ids": [node_id], "confidence": 1.0}
            for node_id in _path_to(hierarchy, expected[0])[1:]
        ]
    llm = ModelPayloadLLM({CatalogTraversalDecision: decisions})
    return HierarchicalCatalogRetriever(
        hierarchy=hierarchy,
        llm_client_factory=lambda: llm,
        max_depth=context.settings.knowledge_hierarchy_max_depth,
        max_branches=context.settings.knowledge_hierarchy_max_branches,
        min_confidence=context.settings.knowledge_hierarchy_min_confidence,
        top_k=case.k,
    ).retrieve(case.question)


def _path_to(hierarchy: CatalogHierarchy, node_id: str) -> tuple[str, ...]:
    path = [node_id]
    current = hierarchy.document(node_id).node
    while current.parent is not None:
        path.append(current.parent)
        current = hierarchy.document(current.parent).node
    path.reverse()
    return tuple(path)
