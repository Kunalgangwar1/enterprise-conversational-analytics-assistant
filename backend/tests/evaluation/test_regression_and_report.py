from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.evaluation.models import (
    EvaluationMetric,
    EvaluationProfile,
    EvaluationRunMetadata,
    EvaluationRunReport,
    RegressionPolicy,
    RegressionStatus,
)
from app.evaluation.regression import compare_report, write_baseline
from app.evaluation.report import redact_sensitive, render_markdown, write_reports


def _report(value: float, *, hard_value: float = 0.0) -> EvaluationRunReport:
    return EvaluationRunReport(
        metadata=EvaluationRunMetadata(
            run_id="20260916T000000Z-offline",
            timestamp=datetime(2026, 9, 16, tzinfo=UTC),
            profile=EvaluationProfile.OFFLINE,
            dataset_versions={"routing": "1.0"},
            python_version="3.11",
            random_seed=42,
        ),
        suites=(),
        metrics=(
            EvaluationMetric(name="routing.accuracy", value=value),
            EvaluationMetric(
                name="privacy.leaks",
                value=hard_value,
                direction="lower_is_better",
                hard_gate=True,
            ),
        ),
        total_cases=1,
        passed=1,
        failed=0,
        skipped=0,
        errors=0,
        pass_rate=1,
        latency_ms={"mean": 1, "p50": 1, "p95": 1, "max": 1},
    )


@pytest.mark.parametrize(
    ("baseline", "current", "allowed", "status"),
    [
        (0.8, 0.9, 0.0, RegressionStatus.IMPROVEMENT),
        (0.8, 0.8, 0.0, RegressionStatus.UNCHANGED),
        (0.8, 0.79, 0.02, RegressionStatus.PASS),
        (0.8, 0.7, 0.02, RegressionStatus.REGRESSION),
    ],
)
def test_higher_is_better_regression_states(baseline, current, allowed, status) -> None:
    result = compare_report(
        _report(current),
        _report(baseline),
        (
            RegressionPolicy(
                metric="routing.accuracy",
                direction="higher_is_better",
                allowed_degradation=allowed,
            ),
        ),
    )

    assert result.results[0].status is status


def test_lower_is_better_and_hard_gate_exit_status() -> None:
    result = compare_report(
        _report(0.8, hard_value=1),
        _report(0.8),
        (
            RegressionPolicy(
                metric="privacy.leaks",
                direction="lower_is_better",
                hard_gate=True,
            ),
        ),
    )

    assert result.status is RegressionStatus.REGRESSION
    assert _report(0.8, hard_value=1).exit_code == 1


def test_baseline_write_requires_explicit_overwrite(tmp_path: Path) -> None:
    target = tmp_path / "baseline.json"
    write_baseline(_report(0.8), target)

    with pytest.raises(FileExistsError):
        write_baseline(_report(0.9), target)

    write_baseline(_report(0.9), target, overwrite=True)
    assert "0.9" in target.read_text(encoding="utf-8")


def test_json_and_markdown_reports_are_serializable(tmp_path: Path) -> None:
    report = _report(0.8)
    run_dir = write_reports(report, tmp_path)

    assert (run_dir / "report.json").is_file()
    assert "Evaluation Summary" in render_markdown(report)
    assert (run_dir / "summary.md").is_file()


def test_report_redaction_removes_secret_fields() -> None:
    payload = redact_sensitive(
        {"api_key": "secret-value", "database_password": "db-secret", "safe": "visible"}
    )

    assert payload == {
        "api_key": "[REDACTED]",
        "database_password": "[REDACTED]",
        "safe": "visible",
    }
