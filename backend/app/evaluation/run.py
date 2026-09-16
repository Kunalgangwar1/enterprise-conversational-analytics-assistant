"""Command-line entry point for offline, integration, and live evaluation."""

import argparse
import sys
from pathlib import Path

from app.core.config import get_settings
from app.evaluation.config import EvaluationConfig
from app.evaluation.models import EvaluationProfile
from app.evaluation.regression import write_baseline
from app.evaluation.report import write_reports
from app.evaluation.runner import run_evaluation


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run synthetic application evaluations")
    parser.add_argument(
        "--profile", choices=[item.value for item in EvaluationProfile], default="offline"
    )
    parser.add_argument("--suite")
    parser.add_argument("--case-id")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--compare-baseline", type=Path)
    parser.add_argument("--write-baseline", type=Path)
    parser.add_argument("--overwrite-baseline", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = get_settings()
    profile = EvaluationProfile(args.profile)
    config = EvaluationConfig.from_settings(settings, output_dir=args.output_dir)
    try:
        report = run_evaluation(
            profile=profile,
            settings=settings,
            config=config,
            suite=args.suite,
            case_id=args.case_id,
            baseline_path=args.compare_baseline,
        )
        run_dir = write_reports(report, config.output_dir)
        if args.write_baseline:
            write_baseline(report, args.write_baseline, overwrite=args.overwrite_baseline)
    except Exception as exc:
        print(f"Evaluation setup failed: {exc}", file=sys.stderr)
        return 2
    print(f"Evaluation Profile: {profile.value}")
    print(
        f"Cases: {report.total_cases} total, {report.passed} passed, "
        f"{report.failed} failed, {report.errors} errors, {report.skipped} skipped"
    )
    for suite_result in report.suites:
        concise = ", ".join(
            f"{name}={value:.4g}"
            for name, value in sorted(suite_result.metrics.items())
            if not name.startswith("confusion.")
        )
        print(f"{suite_result.suite}: {concise}")
    if report.regression:
        print(f"Regression: {report.regression.status.value}")
    print(f"Reports: {run_dir}")
    return report.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
