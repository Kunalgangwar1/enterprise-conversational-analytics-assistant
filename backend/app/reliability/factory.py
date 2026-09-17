"""Build reliability primitives from the repository settings contract."""

from app.core.config import Settings
from app.reliability.circuit_breaker import CircuitBreaker, CircuitBreakerConfig
from app.reliability.policy import RetryPolicy, RetryPolicyConfig


def build_provider_retry_policy(settings: Settings) -> RetryPolicy:
    return RetryPolicy(
        RetryPolicyConfig(
            max_attempts=settings.llm_max_retries + 1,
            initial_delay_seconds=settings.llm_retry_initial_delay_seconds,
            max_delay_seconds=settings.llm_retry_max_delay_seconds,
            max_total_delay_seconds=settings.llm_retry_max_total_delay_seconds,
            jitter_ratio=settings.llm_retry_jitter_ratio,
            operation_timeout_seconds=settings.llm_operation_timeout_seconds,
            request_timeout_seconds=settings.llm_timeout_seconds,
        ),
        circuit_breaker=CircuitBreaker(
            CircuitBreakerConfig(
                enabled=settings.llm_circuit_breaker_enabled,
                failure_threshold=settings.llm_circuit_failure_threshold,
                recovery_timeout_seconds=settings.llm_circuit_recovery_timeout_seconds,
                half_open_max_calls=settings.llm_circuit_half_open_max_calls,
            )
        ),
    )
