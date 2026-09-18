"""Convert Locust CSV output into reviewable JSON and Markdown artifacts."""

import argparse
import csv
import importlib.metadata
import json
import os
import platform
import sys
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from performance.profiles import get_profile
from performance.thresholds import RequestMetrics, Thresholds, threshold_failures


def _number(row: dict[str, str], *names: str) -> float:
    for name in names:
        value = row.get(name)
        if value not in (None, ""):
            return float(value)
    return 0.0


def read_stats(path: Path) -> list[RequestMetrics]:
    """Read stable metrics from Locust's versioned CSV contract."""

    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    return [
        RequestMetrics(
            name=row["Name"],
            request_count=int(_number(row, "Request Count")),
            failure_count=int(_number(row, "Failure Count")),
            average_ms=_number(row, "Average Response Time"),
            maximum_ms=_number(row, "Max Response Time"),
            p50_ms=_number(row, "50%"),
            p90_ms=_number(row, "90%"),
            p95_ms=_number(row, "95%"),
            p99_ms=_number(row, "99%"),
            requests_per_second=_number(row, "Requests/s"),
        )
        for row in rows
        if row.get("Name")
    ]


def write_report(
    *, profile_name: str, stats_path: Path, output_dir: Path, thresholds: Thresholds
) -> list[str]:
    profile = get_profile(profile_name)
    metrics = read_stats(stats_path)
    failures = threshold_failures(metrics, thresholds)
    metadata = {
        "generated_at": datetime.now(UTC).isoformat(),
        "profile": asdict(profile),
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "locust": importlib.metadata.version("locust"),
            "commit_sha": os.getenv("PERFORMANCE_COMMIT_SHA", "unrecorded"),
            "dataset": os.getenv("PERFORMANCE_DATASET", "synthetic-default-seed"),
            "dataset_size": os.getenv("PERFORMANCE_DATASET_SIZE", "default seed configuration"),
            "backend_docker_size_bytes": os.getenv(
                "PERFORMANCE_BACKEND_DOCKER_SIZE_BYTES", "not measured"
            ),
            "frontend_initial_entrypoint_bytes": os.getenv(
                "PERFORMANCE_FRONTEND_ENTRYPOINT_BYTES", "not measured"
            ),
        },
        "thresholds": asdict(thresholds),
        "metrics": [asdict(item) | {"failure_rate": item.failure_rate} for item in metrics],
        "threshold_failures": failures,
        "passed": not failures,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "report.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    lines = [
        f"# Performance report: {profile.name}",
        "",
        f"Generated: `{metadata['generated_at']}`",
        "",
        (
            "| Request | Count | Failures | p50 ms | p90 ms | p95 ms | p99 ms | "
            "Avg ms | Max ms | RPS |"
        ),
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for item in metrics:
        lines.append(
            f"| {item.name} | {item.request_count} | {item.failure_count} | {item.p50_ms:.1f} | "
            f"{item.p90_ms:.1f} | {item.p95_ms:.1f} | {item.p99_ms:.1f} | "
            f"{item.average_ms:.1f} | {item.maximum_ms:.1f} | {item.requests_per_second:.2f} |"
        )
    lines.extend(["", "## Threshold result", ""])
    lines.extend(f"- FAIL: {failure}" for failure in failures)
    if not failures:
        lines.append("- PASS")
    (output_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", required=True)
    parser.add_argument("--stats", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--maximum-failure-rate", type=float, default=0.01)
    parser.add_argument("--maximum-p95-ms", type=float, default=1_500)
    parser.add_argument("--maximum-p99-ms", type=float, default=3_000)
    args = parser.parse_args()
    failures = write_report(
        profile_name=args.profile,
        stats_path=args.stats,
        output_dir=args.output,
        thresholds=Thresholds(
            maximum_failure_rate=args.maximum_failure_rate,
            maximum_p95_ms=args.maximum_p95_ms,
            maximum_p99_ms=args.maximum_p99_ms,
        ),
    )
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
