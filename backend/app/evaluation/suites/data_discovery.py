"""Deterministic dataset discovery ranking evaluation."""

from app.data_discovery.factory import build_data_discovery_service
from app.evaluation.metrics import hit_at_k, recall_at_k, reciprocal_rank
from app.evaluation.models import DiscoveryCase, EvaluationDataset, EvaluationSuiteResult
from app.evaluation.suites.base import SuiteContext, evaluate_cases, mean_case_metric, pass_fail


def evaluate(dataset: EvaluationDataset, context: SuiteContext) -> EvaluationSuiteResult:
    service = build_data_discovery_service(context.settings)

    def one(raw_case):
        case = DiscoveryCase.model_validate(raw_case)
        actual = [item.dataset for item in service.search(case.question).matches]
        expected = case.expected_datasets
        top1 = hit_at_k(actual, expected, 1)
        recall = recall_at_k(actual, expected, case.k)
        rank = reciprocal_rank(actual, expected)
        return pass_fail(
            case,
            bool(top1) if expected else not actual,
            metrics={"top1": top1, "recall_at_k": recall, "mrr": rank},
            expected=", ".join(expected) or "no match",
            actual=", ".join(actual) or "no match",
        )

    return evaluate_cases(
        dataset,
        one,
        lambda items: {
            "top1_accuracy": mean_case_metric(items, "top1"),
            "recall_at_k": mean_case_metric(items, "recall_at_k"),
            "mrr": mean_case_metric(items, "mrr"),
        },
    )
