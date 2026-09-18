"""Local regression gates over normalized Locust request metrics."""

from dataclasses import dataclass


@dataclass(frozen=True)
class RequestMetrics:
    name: str
    request_count: int
    failure_count: int
    average_ms: float
    maximum_ms: float
    p50_ms: float
    p90_ms: float
    p95_ms: float
    p99_ms: float
    requests_per_second: float

    @property
    def failure_rate(self) -> float:
        return self.failure_count / self.request_count if self.request_count else 0.0


@dataclass(frozen=True)
class Thresholds:
    maximum_failure_rate: float = 0.01
    maximum_p95_ms: float = 1_500.0
    maximum_p99_ms: float = 3_000.0
    health_p95_ms: float = 250.0
    health_p99_ms: float = 500.0
    discovery_p95_ms: float = 750.0
    discovery_p99_ms: float = 1_500.0
    session_p95_ms: float = 750.0
    session_p99_ms: float = 1_500.0

    def latency_limits(self, request_name: str) -> tuple[float, float]:
        if request_name == "GET /api/health":
            return self.health_p95_ms, self.health_p99_ms
        if request_name == "POST /api/data-discovery/query":
            return self.discovery_p95_ms, self.discovery_p99_ms
        if request_name == "POST /chat/select-mode":
            return self.session_p95_ms, self.session_p99_ms
        return self.maximum_p95_ms, self.maximum_p99_ms


def threshold_failures(
    metrics: list[RequestMetrics], thresholds: Thresholds | None = None
) -> list[str]:
    """Return deterministic, human-readable violations for aggregate or request rows."""

    thresholds = thresholds or Thresholds()
    failures: list[str] = []
    for metric in metrics:
        maximum_p95_ms, maximum_p99_ms = thresholds.latency_limits(metric.name)
        if metric.failure_rate > thresholds.maximum_failure_rate:
            failures.append(f"{metric.name}: failure rate {metric.failure_rate:.3%}")
        if metric.p95_ms > maximum_p95_ms:
            failures.append(f"{metric.name}: p95 {metric.p95_ms:.1f} ms")
        if metric.p99_ms > maximum_p99_ms:
            failures.append(f"{metric.name}: p99 {metric.p99_ms:.1f} ms")
    return failures
