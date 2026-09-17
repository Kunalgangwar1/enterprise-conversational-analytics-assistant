"""Small process-local, concurrency-safe provider circuit breaker."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from threading import Lock
from time import monotonic

from app.reliability.errors import CircuitOpenError


class CircuitState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass(frozen=True)
class CircuitBreakerConfig:
    enabled: bool = True
    failure_threshold: int = 5
    recovery_timeout_seconds: float = 30.0
    half_open_max_calls: int = 1

    def __post_init__(self) -> None:
        if self.failure_threshold < 1:
            raise ValueError("failure_threshold must be at least one")
        if self.recovery_timeout_seconds <= 0:
            raise ValueError("recovery_timeout_seconds must be positive")
        if self.half_open_max_calls < 1:
            raise ValueError("half_open_max_calls must be at least one")


class CircuitBreaker:
    """Track logical provider-call failures without distributed coordination."""

    def __init__(
        self,
        config: CircuitBreakerConfig,
        *,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        self._config = config
        self._clock = clock
        self._lock = Lock()
        self._state = CircuitState.CLOSED
        self._consecutive_failures = 0
        self._opened_at: float | None = None
        self._half_open_in_flight = 0

    @property
    def state(self) -> CircuitState:
        with self._lock:
            return self._state

    def before_call(self) -> None:
        if not self._config.enabled:
            return
        with self._lock:
            if self._state is CircuitState.OPEN:
                opened_at = self._opened_at if self._opened_at is not None else self._clock()
                if self._clock() - opened_at < self._config.recovery_timeout_seconds:
                    raise CircuitOpenError("Provider circuit is open")
                self._state = CircuitState.HALF_OPEN
                self._half_open_in_flight = 0
            if self._state is CircuitState.HALF_OPEN:
                if self._half_open_in_flight >= self._config.half_open_max_calls:
                    raise CircuitOpenError("Provider circuit trial capacity is exhausted")
                self._half_open_in_flight += 1

    def record_success(self) -> None:
        if not self._config.enabled:
            return
        with self._lock:
            self._state = CircuitState.CLOSED
            self._consecutive_failures = 0
            self._opened_at = None
            self._half_open_in_flight = 0

    def record_failure(self) -> None:
        if not self._config.enabled:
            return
        with self._lock:
            if self._state is CircuitState.HALF_OPEN:
                self._open()
                return
            self._consecutive_failures += 1
            if self._consecutive_failures >= self._config.failure_threshold:
                self._open()

    def record_ignored(self) -> None:
        """Treat a deterministic provider response as proof that the service is reachable."""

        self.record_success()

    def _open(self) -> None:
        self._state = CircuitState.OPEN
        self._opened_at = self._clock()
        self._half_open_in_flight = 0
