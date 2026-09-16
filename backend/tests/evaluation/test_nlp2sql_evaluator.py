from app.core.config import Settings
from app.evaluation.models import (
    CaseStatus,
    EvaluationDataset,
    EvaluationProfile,
    NLP2SQLCase,
)
from app.evaluation.suites.base import SuiteContext
from app.evaluation.suites.nlp2sql import evaluate


def _case(reference_count: int) -> NLP2SQLCase:
    return NLP2SQLCase(
        case_id="sql-semantic-001",
        suite="nlp2sql",
        description="Equivalent SQL text is not required",
        question="Count claims",
        selected_domains=("claims",),
        selected_tables=("claims",),
        candidate_sql="SELECT COUNT(id) AS claim_count FROM claims",
        reference_sql="SELECT COUNT(*) AS claim_count FROM claims",
        candidate_result=[{"claim_count": 4}],
        reference_result=[{"claim_count": reference_count}],
    )


def _evaluate(case: NLP2SQLCase):
    dataset = EvaluationDataset(dataset_version="test", suite="nlp2sql", cases=(case,))
    return evaluate(
        dataset,
        SuiteContext(profile=EvaluationProfile.OFFLINE, settings=Settings(), random_seed=42),
    ).cases[0]


def test_different_sql_with_identical_results_is_correct() -> None:
    result = _evaluate(_case(4))

    assert result.status is CaseStatus.PASSED
    assert result.metrics["result_equivalent"] == 1
    assert result.metrics["reference_sql_isolated"] == 1


def test_executable_but_analytically_wrong_result_fails() -> None:
    result = _evaluate(_case(5))

    assert result.status is CaseStatus.FAILED
    assert result.metrics["result_equivalent"] == 0
