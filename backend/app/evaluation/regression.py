"""Explicit baseline writing and metric regression comparison."""

import json
from pathlib import Path

from app.evaluation.models import (
    EvaluationRunReport,
    RegressionPolicy,
    RegressionResult,
    RegressionStatus,
    RegressionSummary,
)


def compare_report(
    current: EvaluationRunReport,
    baseline: EvaluationRunReport,
    policies: tuple[RegressionPolicy, ...],
) -> RegressionSummary:
    current_metrics = {item.name: item.value for item in current.metrics}
    baseline_metrics = {item.name: item.value for item in baseline.metrics}
    results: list[RegressionResult] = []
    for policy in policies:
        if policy.metric not in current_metrics or policy.metric not in baseline_metrics:
            continue
        current_value = current_metrics[policy.metric]
        baseline_value = baseline_metrics[policy.metric]
        difference = current_value - baseline_value
        degradation = -difference if policy.direction == "higher_is_better" else difference
        if abs(difference) < 1e-12:
            status = RegressionStatus.UNCHANGED
        elif degradation > policy.allowed_degradation:
            status = RegressionStatus.REGRESSION
        elif degradation < 0:
            status = RegressionStatus.IMPROVEMENT
        else:
            status = RegressionStatus.PASS
        results.append(
            RegressionResult(
                metric=policy.metric,
                baseline_value=baseline_value,
                current_value=current_value,
                difference=difference,
                allowed_degradation=policy.allowed_degradation,
                status=status,
            )
        )
    overall = (
        RegressionStatus.REGRESSION
        if any(item.status is RegressionStatus.REGRESSION for item in results)
        else RegressionStatus.PASS
    )
    return RegressionSummary(status=overall, results=tuple(results))


def load_report(path: Path) -> EvaluationRunReport:
    return EvaluationRunReport.model_validate_json(path.read_text(encoding="utf-8"))


def write_baseline(report: EvaluationRunReport, path: Path, *, overwrite: bool = False) -> None:
    if path.exists() and not overwrite:
        raise FileExistsError(f"Baseline already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
