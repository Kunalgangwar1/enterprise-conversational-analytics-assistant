"""Shared suite execution context and safe case execution helpers."""

from collections.abc import Callable
from dataclasses import dataclass
from time import perf_counter
from typing import Protocol

from app.core.config import Settings
from app.evaluation.models import (
    BaseEvaluationCase,
    CaseStatus,
    EvaluationCaseResult,
    EvaluationDataset,
    EvaluationProfile,
    EvaluationSuiteResult,
)
from app.llm.exceptions import LLMError


@dataclass(frozen=True, slots=True)
class SuiteContext:
    profile: EvaluationProfile
    settings: Settings
    random_seed: int


class SuiteEvaluator(Protocol):
    def __call__(
        self, dataset: EvaluationDataset, context: SuiteContext
    ) -> EvaluationSuiteResult: ...


def evaluate_cases(
    dataset: EvaluationDataset,
    evaluator: Callable[[BaseEvaluationCase], EvaluationCaseResult],
    metric_builder: Callable[[tuple[EvaluationCaseResult, ...]], dict[str, float]],
) -> EvaluationSuiteResult:
    results: list[EvaluationCaseResult] = []
    for case in dataset.cases:
        started = perf_counter()
        try:
            result = evaluator(case)
        except Exception as exc:
            provider_error = isinstance(exc, LLMError) or any(
                label in type(exc).__name__ for label in ("Provider", "RateLimit", "Timeout")
            )
            result = EvaluationCaseResult(
                case_id=case.case_id,
                suite=case.suite,
                status=CaseStatus.ERROR,
                elapsed_ms=0,
                error_type=type(exc).__name__,
                error=str(exc)[:300] or "Evaluation case raised an error",
                provider_error=provider_error,
            )
        elapsed = (perf_counter() - started) * 1_000
        results.append(result.model_copy(update={"elapsed_ms": elapsed}))
    frozen = tuple(results)
    return EvaluationSuiteResult(
        suite=dataset.suite,
        dataset_version=dataset.dataset_version,
        cases=frozen,
        metrics=metric_builder(frozen),
    )


def pass_fail(
    case: BaseEvaluationCase,
    passed: bool,
    *,
    metrics: dict[str, float] | None = None,
    expected: str | None = None,
    actual: str | None = None,
    error: str | None = None,
) -> EvaluationCaseResult:
    return EvaluationCaseResult(
        case_id=case.case_id,
        suite=case.suite,
        status=CaseStatus.PASSED if passed else CaseStatus.FAILED,
        elapsed_ms=0,
        metrics=metrics or {},
        expected=expected,
        actual=actual,
        error=error,
    )


def mean_case_metric(results: tuple[EvaluationCaseResult, ...], name: str) -> float:
    values = [item.metrics[name] for item in results if name in item.metrics]
    return sum(values) / len(values) if values else 0.0
