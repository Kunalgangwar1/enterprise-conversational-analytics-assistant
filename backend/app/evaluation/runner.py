"""Evaluation run orchestration outside the production request path."""

from __future__ import annotations

import platform
import random
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import yaml

from app.core.config import Settings
from app.evaluation.config import EvaluationConfig
from app.evaluation.loader import load_datasets
from app.evaluation.metrics import latency_summary
from app.evaluation.models import (
    CaseStatus,
    EvaluationMetric,
    EvaluationProfile,
    EvaluationRunMetadata,
    EvaluationRunReport,
    RegressionPolicy,
)
from app.evaluation.regression import compare_report, load_report
from app.evaluation.suites import SUITE_EVALUATORS, SuiteContext

_HARD_ZERO_METRICS = {
    "privacy_leak_count",
    "unsafe_execution_count",
    "invalid_citation_count",
    "budget_violation_count",
    "invalid_tool_count",
    "invalid_distance_count",
    "forecast_invariant_violation_count",
}


def run_evaluation(
    *,
    profile: EvaluationProfile,
    settings: Settings,
    config: EvaluationConfig,
    suite: str | None = None,
    case_id: str | None = None,
    baseline_path: Path | None = None,
) -> EvaluationRunReport:
    if profile is EvaluationProfile.LIVE:
        _validate_live_configuration(settings)
    random.seed(config.random_seed)
    datasets = load_datasets(config.eval_root / "cases", suite=suite, case_id=case_id)
    context = SuiteContext(profile=profile, settings=settings, random_seed=config.random_seed)
    suite_results = tuple(SUITE_EVALUATORS[dataset.suite](dataset, context) for dataset in datasets)
    cases = tuple(case for result in suite_results for case in result.cases)
    passed = sum(case.status is CaseStatus.PASSED for case in cases)
    failed = sum(case.status is CaseStatus.FAILED for case in cases)
    skipped = sum(case.status is CaseStatus.SKIPPED for case in cases)
    errors = sum(case.status is CaseStatus.ERROR for case in cases)
    metrics = tuple(
        EvaluationMetric(
            name=f"{result.suite}.{name}",
            value=value,
            direction="lower_is_better"
            if name.endswith(("count", "mae", "rmse", "smape"))
            else "higher_is_better",
            hard_gate=name in _HARD_ZERO_METRICS,
        )
        for result in suite_results
        for name, value in sorted(result.metrics.items())
        if not name.startswith("confusion.")
    )
    now = datetime.now(UTC)
    report = EvaluationRunReport(
        metadata=EvaluationRunMetadata(
            run_id=f"{now.strftime('%Y%m%dT%H%M%S%fZ')}-{profile.value}",
            timestamp=now,
            profile=profile,
            dataset_versions={item.suite: item.dataset_version for item in datasets},
            git_commit_sha=_git_sha(),
            python_version=platform.python_version(),
            llm_provider=settings.llm_provider if profile is EvaluationProfile.LIVE else None,
            llm_model=_llm_model(settings) if profile is EvaluationProfile.LIVE else None,
            embedding_provider=settings.embedding_provider
            if profile is EvaluationProfile.LIVE
            else None,
            embedding_model=_embedding_model(settings)
            if profile is EvaluationProfile.LIVE
            else None,
            random_seed=config.random_seed,
        ),
        suites=suite_results,
        metrics=metrics,
        total_cases=len(cases),
        passed=passed,
        failed=failed,
        skipped=skipped,
        errors=errors,
        pass_rate=passed / len(cases) if cases else 0.0,
        latency_ms=latency_summary([case.elapsed_ms for case in cases]),
    )
    if baseline_path:
        policies = load_policies(config.eval_root / "config.yaml")
        report = report.model_copy(
            update={"regression": compare_report(report, load_report(baseline_path), policies)}
        )
    return report


def load_policies(path: Path) -> tuple[RegressionPolicy, ...]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    return tuple(RegressionPolicy.model_validate(item) for item in payload.get("policies", []))


def _git_sha() -> str | None:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def _llm_model(settings: Settings) -> str | None:
    if settings.llm_provider == "gemini":
        return settings.gemini_llm_model
    if settings.llm_provider == "azure_openai":
        return settings.azure_openai_deployment
    return None


def _embedding_model(settings: Settings) -> str | None:
    if settings.embedding_provider == "gemini":
        return settings.gemini_embedding_model
    if settings.embedding_provider == "azure_openai":
        return settings.azure_openai_embedding_deployment
    return None


def _validate_live_configuration(settings: Settings) -> None:
    """Validate real provider configuration without falling back or sending requests."""

    from app.knowledge_catalog.embeddings.factory import create_embedding_client
    from app.llm.factory import create_llm_client

    create_llm_client(settings)
    create_embedding_client(settings)
