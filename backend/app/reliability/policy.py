"""Selective bounded retries with exponential backoff, jitter, and Retry-After."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from random import Random
from time import monotonic, sleep
from typing import TypeVar

from app.observability.metrics import get_metrics
from app.observability.tracing import start_span
from app.reliability.circuit_breaker import CircuitBreaker
from app.reliability.errors import (
    CircuitOpenError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)

_ResultT = TypeVar("_ResultT")
_RETRYABLE = (ProviderTimeoutError, ProviderRateLimitError, ProviderUnavailableError)


@dataclass(frozen=True)
class RetryPolicyConfig:
    max_attempts: int = 3
    initial_delay_seconds: float = 0.5
    max_delay_seconds: float = 8.0
    max_total_delay_seconds: float = 15.0
    jitter_ratio: float = 0.20
    operation_timeout_seconds: float = 90.0
    request_timeout_seconds: float = 30.0

    @property
    def worst_case_duration_seconds(self) -> float:
        """Return the configured upper bound without performing real waits."""

        attempt_budget = self.max_attempts * self.request_timeout_seconds
        return min(
            self.operation_timeout_seconds,
            attempt_budget + self.max_total_delay_seconds,
        )

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be at least one")
        if self.initial_delay_seconds < 0:
            raise ValueError("initial_delay_seconds cannot be negative")
        if self.max_delay_seconds < self.initial_delay_seconds:
            raise ValueError("max_delay_seconds cannot be below initial_delay_seconds")
        if self.max_total_delay_seconds < 0:
            raise ValueError("max_total_delay_seconds cannot be negative")
        if not 0 <= self.jitter_ratio <= 1:
            raise ValueError("jitter_ratio must be between zero and one")
        if self.request_timeout_seconds <= 0:
            raise ValueError("request_timeout_seconds must be positive")
        if self.operation_timeout_seconds < self.request_timeout_seconds:
            raise ValueError("operation_timeout_seconds must cover one request timeout")


class RetryPolicy:
    """Execute safe provider reads under one bounded logical-call budget."""

    def __init__(
        self,
        config: RetryPolicyConfig,
        *,
        circuit_breaker: CircuitBreaker,
        sleeper: Callable[[float], None] = sleep,
        clock: Callable[[], float] = monotonic,
        random_source: Random | None = None,
    ) -> None:
        self._config = config
        self._circuit = circuit_breaker
        self._sleep = sleeper
        self._clock = clock
        self._random = random_source or Random()

    def execute(
        self,
        action: Callable[[], _ResultT],
        *,
        provider: str,
        operation: str,
    ) -> _ResultT:
        metrics = get_metrics()
        try:
            self._circuit.before_call()
        except CircuitOpenError:
            metrics.record(
                "provider.circuit_open",
                1,
                {"provider": provider, "operation": operation, "reason_code": "circuit_open"},
            )
            raise

        started = self._clock()
        total_delay = 0.0
        with start_span(
            "provider.call",
            {"gen_ai.provider.name": provider, "operation.name": operation},
        ) as span:
            for attempt in range(1, self._config.max_attempts + 1):
                try:
                    result = action()
                except _RETRYABLE as exc:
                    reason = _reason_code(exc)
                    self._record_failure_signal(provider, operation, reason)
                    if not self._can_retry(attempt, started):
                        self._circuit.record_failure()
                        span.set_attribute("retry_count", attempt - 1)
                        span.set_attribute("outcome", reason)
                        raise
                    delay = self.delay_for(
                        retry_number=attempt,
                        retry_after_seconds=exc.retry_after_seconds,
                        total_delay_seconds=total_delay,
                    )
                    remaining = self._remaining_operation_time(started)
                    delay = min(delay, max(0.0, remaining - self._config.request_timeout_seconds))
                    if delay <= 0:
                        self._circuit.record_failure()
                        span.set_attribute("retry_count", attempt - 1)
                        span.set_attribute("outcome", reason)
                        raise
                    metrics.record(
                        "provider.retries",
                        1,
                        {"provider": provider, "operation": operation, "reason_code": reason},
                    )
                    self._sleep(delay)
                    total_delay += delay
                    continue
                except Exception:
                    self._circuit.record_ignored()
                    raise
                self._circuit.record_success()
                span.set_attribute("retry_count", attempt - 1)
                span.set_attribute("outcome", "success")
                return result
        raise AssertionError("retry loop terminated unexpectedly")

    def delay_for(
        self,
        *,
        retry_number: int,
        retry_after_seconds: float | None,
        total_delay_seconds: float,
    ) -> float:
        exponential = min(
            self._config.initial_delay_seconds * (2 ** max(0, retry_number - 1)),
            self._config.max_delay_seconds,
        )
        jitter = exponential * self._config.jitter_ratio
        delayed = exponential + self._random.uniform(-jitter, jitter)
        if retry_after_seconds is not None and retry_after_seconds >= 0:
            delayed = max(delayed, retry_after_seconds)
        remaining_delay = max(0.0, self._config.max_total_delay_seconds - total_delay_seconds)
        return min(max(0.0, delayed), self._config.max_delay_seconds, remaining_delay)

    def _can_retry(self, attempt: int, started: float) -> bool:
        if attempt >= self._config.max_attempts:
            return False
        return self._remaining_operation_time(started) >= self._config.request_timeout_seconds

    def _remaining_operation_time(self, started: float) -> float:
        return max(0.0, self._config.operation_timeout_seconds - (self._clock() - started))

    @staticmethod
    def _record_failure_signal(provider: str, operation: str, reason: str) -> None:
        metric = {
            "timeout": "provider.timeouts",
            "rate_limited": "provider.unavailable",
            "unavailable": "provider.unavailable",
        }[reason]
        get_metrics().record(
            metric,
            1,
            {"provider": provider, "operation": operation, "reason_code": reason},
        )


def _reason_code(error: Exception) -> str:
    if isinstance(error, ProviderTimeoutError):
        return "timeout"
    if isinstance(error, ProviderRateLimitError):
        return "rate_limited"
    return "unavailable"
