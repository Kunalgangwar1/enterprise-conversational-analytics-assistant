from __future__ import annotations

from random import Random

import pytest

import app.reliability.policy as policy_module
from app.reliability.circuit_breaker import CircuitBreaker, CircuitBreakerConfig
from app.reliability.errors import (
    CircuitOpenError,
    ProviderAuthenticationError,
    ProviderRateLimitError,
    ProviderRequestError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from app.reliability.policy import RetryPolicy, RetryPolicyConfig


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0
        self.delays: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, delay: float) -> None:
        self.delays.append(delay)
        self.now += delay


class RecordingMetrics:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    def record(
        self,
        name: str,
        value: int | float = 1,
        attributes: dict[str, object] | None = None,
    ) -> None:
        del value
        self.calls.append((name, attributes or {}))


def _policy(
    clock: FakeClock,
    *,
    attempts: int = 3,
    initial_delay: float = 0.5,
    max_delay: float = 4.0,
    max_total_delay: float = 10.0,
) -> RetryPolicy:
    return RetryPolicy(
        RetryPolicyConfig(
            max_attempts=attempts,
            initial_delay_seconds=initial_delay,
            max_delay_seconds=max_delay,
            max_total_delay_seconds=max_total_delay,
            jitter_ratio=0,
            operation_timeout_seconds=30,
            request_timeout_seconds=1,
        ),
        circuit_breaker=CircuitBreaker(CircuitBreakerConfig(enabled=False), clock=clock),
        sleeper=clock.sleep,
        clock=clock,
        random_source=Random(27),
    )


@pytest.mark.parametrize(
    ("error", "expected_metric"),
    [
        pytest.param(ProviderTimeoutError("safe timeout"), "provider.timeouts", id="timeout"),
        pytest.param(ProviderRateLimitError("HTTP 429"), "provider.unavailable", id="http-429"),
        pytest.param(ProviderUnavailableError("HTTP 503"), "provider.unavailable", id="http-503"),
    ],
)
def test_transient_failures_are_retried_and_observable(
    error: Exception,
    expected_metric: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = FakeClock()
    metrics = RecordingMetrics()
    monkeypatch.setattr(policy_module, "get_metrics", lambda: metrics)
    outcomes: list[object] = [error, "success"]

    def action() -> str:
        result = outcomes.pop(0)
        if isinstance(result, Exception):
            raise result
        return str(result)

    assert _policy(clock).execute(action, provider="gemini", operation="generate") == "success"
    assert clock.delays == [0.5]
    assert [name for name, _ in metrics.calls] == [expected_metric, "provider.retries"]


@pytest.mark.parametrize(
    "error",
    [
        pytest.param(ProviderAuthenticationError("authentication failed"), id="authentication"),
        pytest.param(ProviderRequestError("HTTP 400"), id="http-400"),
        pytest.param(ValueError("programming error"), id="programming-error"),
    ],
)
def test_non_retryable_failures_are_not_retried(error: Exception) -> None:
    clock = FakeClock()
    calls = 0

    def action() -> None:
        nonlocal calls
        calls += 1
        raise error

    with pytest.raises(type(error)):
        _policy(clock).execute(action, provider="gemini", operation="generate")
    assert calls == 1
    assert clock.delays == []


def test_attempt_count_is_bounded() -> None:
    clock = FakeClock()
    calls = 0

    def action() -> None:
        nonlocal calls
        calls += 1
        raise ProviderUnavailableError("unavailable")

    with pytest.raises(ProviderUnavailableError):
        _policy(clock, attempts=3).execute(action, provider="gemini", operation="generate")
    assert calls == 3
    assert clock.delays == [0.5, 1.0]


def test_exponential_delay_and_total_budget_are_bounded() -> None:
    clock = FakeClock()
    policy = _policy(clock, initial_delay=2, max_delay=3, max_total_delay=4)
    assert policy.delay_for(retry_number=1, retry_after_seconds=None, total_delay_seconds=0) == 2
    assert policy.delay_for(retry_number=2, retry_after_seconds=None, total_delay_seconds=2) == 2
    assert policy.delay_for(retry_number=4, retry_after_seconds=None, total_delay_seconds=4) == 0


def test_retry_after_is_respected_within_configured_bounds() -> None:
    clock = FakeClock()
    policy = _policy(clock, max_delay=4, max_total_delay=4)
    assert policy.delay_for(retry_number=1, retry_after_seconds=3, total_delay_seconds=0) == 3
    assert policy.delay_for(retry_number=1, retry_after_seconds=30, total_delay_seconds=0) == 4


def test_operation_budget_prevents_another_full_request_attempt() -> None:
    clock = FakeClock()
    policy = RetryPolicy(
        RetryPolicyConfig(
            max_attempts=3,
            initial_delay_seconds=0.5,
            max_delay_seconds=1,
            max_total_delay_seconds=1,
            jitter_ratio=0,
            operation_timeout_seconds=1,
            request_timeout_seconds=1,
        ),
        circuit_breaker=CircuitBreaker(CircuitBreakerConfig(enabled=False), clock=clock),
        sleeper=clock.sleep,
        clock=clock,
    )
    calls = 0

    def action() -> None:
        nonlocal calls
        calls += 1
        raise ProviderTimeoutError("timeout")

    with pytest.raises(ProviderTimeoutError):
        policy.execute(action, provider="gemini", operation="generate")
    assert calls == 1


def test_worst_case_time_budget_is_derived_without_wall_clock_sleep() -> None:
    config = RetryPolicyConfig(
        max_attempts=3,
        initial_delay_seconds=1,
        max_delay_seconds=4,
        max_total_delay_seconds=7,
        jitter_ratio=0.2,
        operation_timeout_seconds=20,
        request_timeout_seconds=5,
    )

    assert config.max_attempts * config.request_timeout_seconds == 15
    assert config.worst_case_duration_seconds == 20

    delay_limited = RetryPolicyConfig(
        max_attempts=2,
        initial_delay_seconds=1,
        max_delay_seconds=2,
        max_total_delay_seconds=2,
        jitter_ratio=0,
        operation_timeout_seconds=30,
        request_timeout_seconds=4,
    )
    assert delay_limited.worst_case_duration_seconds == 10


def test_open_circuit_fails_fast_and_records_bounded_metric(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = FakeClock()
    metrics = RecordingMetrics()
    monkeypatch.setattr(policy_module, "get_metrics", lambda: metrics)
    circuit = CircuitBreaker(
        CircuitBreakerConfig(
            failure_threshold=1,
            recovery_timeout_seconds=10,
            half_open_max_calls=1,
        ),
        clock=clock,
    )
    circuit.record_failure()
    policy = RetryPolicy(
        RetryPolicyConfig(
            max_attempts=3,
            operation_timeout_seconds=10,
            request_timeout_seconds=1,
        ),
        circuit_breaker=circuit,
        sleeper=clock.sleep,
        clock=clock,
    )
    calls = 0

    def action() -> None:
        nonlocal calls
        calls += 1

    with pytest.raises(CircuitOpenError):
        policy.execute(action, provider="gemini", operation="generate")

    assert calls == 0
    assert metrics.calls == [
        (
            "provider.circuit_open",
            {
                "provider": "gemini",
                "operation": "generate",
                "reason_code": "circuit_open",
            },
        )
    ]


def test_retry_callable_never_observes_operation_payload() -> None:
    clock = FakeClock()
    secret_prompt = "private member prompt"
    observed: list[str] = []

    def action() -> str:
        observed.append(secret_prompt)
        return "private provider response"

    result = _policy(clock).execute(action, provider="gemini", operation="generate")
    assert result == "private provider response"
    assert observed == [secret_prompt]
