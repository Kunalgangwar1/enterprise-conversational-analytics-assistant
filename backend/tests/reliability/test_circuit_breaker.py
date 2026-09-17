from __future__ import annotations

import pytest

from app.reliability.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitState,
)
from app.reliability.errors import CircuitOpenError


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def _breaker(clock: Clock, *, enabled: bool = True) -> CircuitBreaker:
    return CircuitBreaker(
        CircuitBreakerConfig(
            enabled=enabled,
            failure_threshold=2,
            recovery_timeout_seconds=10,
            half_open_max_calls=1,
        ),
        clock=clock,
    )


def test_circuit_opens_after_failure_threshold_and_fails_fast() -> None:
    clock = Clock()
    circuit = _breaker(clock)
    circuit.before_call()
    circuit.record_failure()
    circuit.before_call()
    circuit.record_failure()
    assert circuit.state is CircuitState.OPEN
    with pytest.raises(CircuitOpenError):
        circuit.before_call()


def test_half_open_success_closes_circuit() -> None:
    clock = Clock()
    circuit = _breaker(clock)
    circuit.record_failure()
    circuit.record_failure()
    clock.now = 10
    circuit.before_call()
    assert circuit.state is CircuitState.HALF_OPEN
    circuit.record_success()
    assert circuit.state is CircuitState.CLOSED


def test_half_open_failure_reopens_and_bounds_trials() -> None:
    clock = Clock()
    circuit = _breaker(clock)
    circuit.record_failure()
    circuit.record_failure()
    clock.now = 10
    circuit.before_call()
    with pytest.raises(CircuitOpenError):
        circuit.before_call()
    circuit.record_failure()
    assert circuit.state is CircuitState.OPEN
    with pytest.raises(CircuitOpenError):
        circuit.before_call()


def test_disabled_circuit_breaker_preserves_calls() -> None:
    circuit = _breaker(Clock(), enabled=False)
    for _ in range(20):
        circuit.before_call()
        circuit.record_failure()
    assert circuit.state is CircuitState.CLOSED
