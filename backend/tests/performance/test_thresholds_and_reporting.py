import json
from pathlib import Path

from performance.report import read_stats, write_report
from performance.thresholds import RequestMetrics, Thresholds, threshold_failures


def _metric(**overrides: float | int | str) -> RequestMetrics:
    values: dict[str, float | int | str] = {
        "name": "GET /api/health",
        "request_count": 100,
        "failure_count": 0,
        "average_ms": 20,
        "maximum_ms": 100,
        "p50_ms": 10,
        "p90_ms": 30,
        "p95_ms": 40,
        "p99_ms": 60,
        "requests_per_second": 10,
    }
    values.update(overrides)
    return RequestMetrics(**values)  # type: ignore[arg-type]


def test_threshold_calculation_reports_each_regression() -> None:
    failures = threshold_failures(
        [_metric(failure_count=2, p95_ms=1_501, p99_ms=3_001)], Thresholds()
    )
    assert len(failures) == 3


def test_thresholds_distinguish_lightweight_and_sql_paths() -> None:
    thresholds = Thresholds()
    assert thresholds.latency_limits("GET /api/health") == (250, 500)
    assert thresholds.latency_limits("POST /chat/execute-sql") == (1_500, 3_000)


def test_csv_read_and_baseline_serialization(tmp_path: Path) -> None:
    stats = tmp_path / "locust_stats.csv"
    stats.write_text(
        "Type,Name,Request Count,Failure Count,Median Response Time,Average Response Time,"
        "Min Response Time,Max Response Time,Average Content Size,Requests/s,Failures/s,"
        "50%,90%,95%,99%\n"
        "GET,GET /api/health,10,0,9,10,5,20,10,2,0,9,14,16,19\n",
        encoding="utf-8",
    )
    parsed = read_stats(stats)
    assert parsed[0].p95_ms == 16

    output = tmp_path / "report"
    assert (
        write_report(
            profile_name="smoke", stats_path=stats, output_dir=output, thresholds=Thresholds()
        )
        == []
    )
    payload = json.loads((output / "report.json").read_text(encoding="utf-8"))
    assert payload["passed"] is True
    assert payload["profile"]["name"] == "smoke"
    assert payload["environment"]["locust"] == "2.46.5"
    assert payload["environment"]["dataset"] == "synthetic-default-seed"
    assert (output / "report.md").is_file()
