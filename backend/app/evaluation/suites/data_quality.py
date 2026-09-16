"""Data Quality evidence retrieval evaluation."""

from functools import partial

from app.data_quality.agent import DataQualityAgent
from app.data_quality.context_builder import DataQualityContextBuilder
from app.data_quality.loader import DataQualityLoader
from app.data_quality.models import DataQualityGroundedAnswer
from app.data_quality.retriever import DataQualityRetriever
from app.evaluation.metrics import hit_at_k, recall_at_k, reciprocal_rank
from app.evaluation.models import EvaluationDataset, EvaluationSuiteResult, RetrievalCase
from app.evaluation.suites.base import SuiteContext, evaluate_cases, mean_case_metric, pass_fail
from app.evaluation.suites.fakes import ModelPayloadLLM
from app.llm.factory import create_llm_client


def evaluate(dataset: EvaluationDataset, context: SuiteContext) -> EvaluationSuiteResult:
    retriever = DataQualityRetriever(
        DataQualityLoader(context.settings.data_quality_dir).load(),
        top_k=context.settings.data_quality_top_k,
    )

    def one(raw_case):
        case = RetrievalCase.model_validate(raw_case)
        evidence = retriever.retrieve(case.question)
        actual = [item.evidence_id for item in evidence]
        expected = case.expected_evidence_ids or case.acceptable_evidence_ids
        no_evidence = float(case.expect_no_evidence and not actual)
        hit = no_evidence or hit_at_k(actual, expected, case.k)
        recall = (
            1.0
            if no_evidence or (case.acceptable_evidence_ids and hit)
            else recall_at_k(actual, expected, case.k)
        )
        if evidence:
            cited_id = evidence[0].evidence_id
            llm_factory = (
                partial(create_llm_client, context.settings)
                if context.profile.value == "live"
                else lambda: ModelPayloadLLM(
                    {
                        DataQualityGroundedAnswer: {
                            "answer": (
                                "The supplied synthetic quality guidance supports this answer."
                            ),
                            "citation_ids": [cited_id],
                        }
                    }
                )
            )
        else:
            llm_factory = partial(create_llm_client, context.settings)
        answer = DataQualityAgent(
            retriever=retriever,
            context_builder=DataQualityContextBuilder(
                max_chars=context.settings.knowledge_context_max_chars
            ),
            llm_client_factory=llm_factory,
        ).answer(case.question)
        invalid_citations = len({item.id for item in answer.citations} - set(actual))
        case_metrics = {
            "hit": float(hit),
            "recall_at_k": recall,
            "mrr": 1.0 if no_evidence else reciprocal_rank(actual, expected),
            "citation_valid": float(invalid_citations == 0),
            "invalid_citations": float(invalid_citations),
        }
        if case.expect_no_evidence:
            case_metrics["no_evidence_correct"] = no_evidence
        return pass_fail(
            case,
            bool(hit) and invalid_citations == 0,
            metrics=case_metrics,
            expected=", ".join(expected) or "no evidence",
            actual=", ".join(actual) or "no evidence",
        )

    return evaluate_cases(
        dataset,
        one,
        lambda items: {
            "evidence_recall_at_k": mean_case_metric(items, "recall_at_k"),
            "mrr": mean_case_metric(items, "mrr"),
            "citation_validity_rate": mean_case_metric(items, "citation_valid"),
            "no_evidence_accuracy": mean_case_metric(items, "no_evidence_correct"),
            "invalid_citation_count": sum(
                item.metrics.get("invalid_citations", 0) for item in items
            ),
        },
    )
