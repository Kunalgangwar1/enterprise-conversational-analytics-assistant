"""Privacy-conscious JSON and Markdown evaluation report artifacts."""

import json
import re
from pathlib import Path
from typing import Any

from app.evaluation.models import EvaluationRunReport

_SECRET_KEY = re.compile(r"(?:api[_-]?key|password|secret|token_mapping)", re.IGNORECASE)


def write_reports(report: EvaluationRunReport, output_root: Path) -> Path:
    run_dir = output_root / report.metadata.run_id
    if run_dir.exists():
        raise FileExistsError(f"Evaluation run directory already exists: {run_dir}")
    run_dir.mkdir(parents=True)
    safe_payload = redact_sensitive(report.model_dump(mode="json"))
    (run_dir / "report.json").write_text(
        json.dumps(safe_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (run_dir / "summary.md").write_text(render_markdown(report), encoding="utf-8")
    return run_dir


def redact_sensitive(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "[REDACTED]" if _SECRET_KEY.search(str(key)) else redact_sensitive(item)
            for key, item in value.items()
        }
    if isinstance(value, list | tuple):
        return [redact_sensitive(item) for item in value]
    return value


def render_markdown(report: EvaluationRunReport) -> str:
    lines = [
        "# Evaluation Summary",
        "",
        f"- Profile: `{report.metadata.profile.value}`",
        f"- Run: `{report.metadata.run_id}`",
        f"- Cases: {report.total_cases} total, {report.passed} passed, "
        f"{report.failed} failed, {report.errors} errors, {report.skipped} skipped",
        f"- Pass rate: {report.pass_rate:.2%}",
        "",
        "## Suite metrics",
        "",
    ]
    for suite in report.suites:
        lines.append(f"### {suite.suite}")
        lines.append("")
        lines.extend(f"- {name}: {value:.6g}" for name, value in sorted(suite.metrics.items()))
        lines.append("")
    failed = [
        case
        for suite in report.suites
        for case in suite.cases
        if case.status.value in {"failed", "error"}
    ]
    if failed:
        lines.extend(["## Failed cases", ""])
        for case in failed:
            reason = case.error or f"expected {case.expected}; actual {case.actual}"
            lines.append(f"- `{case.case_id}` ({case.suite}): {reason}")
        lines.append("")
    lines.extend(["## Latency (milliseconds)", ""])
    lines.extend(f"- {name}: {value:.3f}" for name, value in report.latency_ms.items())
    lines.append("")
    if report.regression:
        lines.extend(["## Regression", "", f"Overall: **{report.regression.status.value}**", ""])
    return "\n".join(lines)
