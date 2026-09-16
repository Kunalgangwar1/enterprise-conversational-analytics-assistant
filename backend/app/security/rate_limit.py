"""Small subject-scoped rate-limit abstraction with memory and Redis backends."""

import hashlib
import math
from collections.abc import Callable
from dataclasses import dataclass
from threading import Lock
from time import monotonic
from typing import Protocol

from fastapi import Request
from redis import Redis
from redis.exceptions import RedisError

from app.api.errors import APIError
from app.auth.models import AuthPrincipal
from app.core.config import Settings
from app.security.exceptions import RateLimitUnavailableError

_FIXED_WINDOW_SCRIPT = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then
  redis.call('EXPIRE', KEYS[1], ARGV[1])
end
local ttl = redis.call('TTL', KEYS[1])
return {count, ttl}
"""


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    remaining: int
    retry_after_seconds: int


class RateLimiter(Protocol):
    def check(self, subject: str, scope: str) -> RateLimitDecision:
        """Consume one request from the subject/scope window."""

        ...

    def close(self) -> None:
        """Release backend resources."""

        ...


class DisabledRateLimiter:
    def check(self, subject: str, scope: str) -> RateLimitDecision:
        del subject, scope
        return RateLimitDecision(allowed=True, remaining=0, retry_after_seconds=0)

    def close(self) -> None:
        pass


class InMemoryRateLimiter:
    """Deterministic process-local fixed-window limiter for local development/tests."""

    def __init__(
        self,
        *,
        requests: int,
        window_seconds: int,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        self._requests = requests
        self._window_seconds = window_seconds
        self._clock = clock
        self._counts: dict[tuple[str, int], int] = {}
        self._lock = Lock()

    def check(self, subject: str, scope: str) -> RateLimitDecision:
        now = self._clock()
        window = int(now // self._window_seconds)
        key = (_hashed_identity(subject, scope), window)
        with self._lock:
            count = self._counts.get(key, 0) + 1
            self._counts[key] = count
            if len(self._counts) > 10_000:
                self._counts = {
                    item_key: value
                    for item_key, value in self._counts.items()
                    if item_key[1] >= window - 1
                }
        retry_after = max(1, math.ceil(self._window_seconds - (now % self._window_seconds)))
        return RateLimitDecision(
            allowed=count <= self._requests,
            remaining=max(0, self._requests - count),
            retry_after_seconds=retry_after,
        )

    def close(self) -> None:
        pass

    def key_for(self, subject: str, scope: str) -> str:
        """Expose the non-reversible in-memory identity for deterministic tests."""

        return _hashed_identity(subject, scope)


class RedisRateLimiter:
    """Atomic Redis fixed-window limiter suitable for shared application replicas."""

    def __init__(
        self,
        redis_url: str,
        *,
        key_prefix: str,
        requests: int,
        window_seconds: int,
        client: Redis | None = None,
    ) -> None:
        self._client = client or Redis.from_url(redis_url, decode_responses=True)
        self._key_prefix = key_prefix.rstrip(":")
        self._requests = requests
        self._window_seconds = window_seconds

    def check(self, subject: str, scope: str) -> RateLimitDecision:
        key = self.key_for(subject, scope)
        try:
            raw_count, raw_ttl = self._client.eval(
                _FIXED_WINDOW_SCRIPT,
                1,
                key,
                self._window_seconds,
            )
        except RedisError as exc:
            raise RateLimitUnavailableError("rate-limit storage is unavailable") from exc
        count = int(raw_count)
        ttl = max(1, int(raw_ttl))
        return RateLimitDecision(
            allowed=count <= self._requests,
            remaining=max(0, self._requests - count),
            retry_after_seconds=ttl,
        )

    def key_for(self, subject: str, scope: str) -> str:
        return f"{self._key_prefix}:{scope}:{_hashed_identity(subject, scope)}"

    def close(self) -> None:
        self._client.close()


def build_rate_limiter(settings: Settings) -> RateLimiter:
    if not settings.rate_limit_enabled:
        return DisabledRateLimiter()
    if settings.rate_limit_backend == "memory":
        return InMemoryRateLimiter(
            requests=settings.rate_limit_requests,
            window_seconds=settings.rate_limit_window_seconds,
        )
    redis_url = settings.rate_limit_redis_url
    if redis_url is None:  # Defensive: Settings validates this first.
        raise ValueError("RATE_LIMIT_REDIS_URL is required for the Redis rate limiter")
    return RedisRateLimiter(
        redis_url.get_secret_value(),
        key_prefix=settings.rate_limit_redis_key_prefix,
        requests=settings.rate_limit_requests,
        window_seconds=settings.rate_limit_window_seconds,
    )


def enforce_rate_limit(request: Request, principal: AuthPrincipal, scope: str) -> None:
    """Apply an authenticated expensive-operation limit with safe HTTP errors."""

    limiter: RateLimiter = request.app.state.rate_limiter
    try:
        decision = limiter.check(principal.subject, scope)
    except RateLimitUnavailableError as exc:
        raise APIError(
            status_code=503,
            code="rate_limit_unavailable",
            message="Request protection is temporarily unavailable.",
        ) from exc
    if not decision.allowed:
        raise APIError(
            status_code=429,
            code="rate_limit_exceeded",
            message="Too many requests; retry after the indicated interval.",
            headers={"Retry-After": str(decision.retry_after_seconds)},
        )


def _hashed_identity(subject: str, scope: str) -> str:
    return hashlib.sha256(f"{len(scope)}:{scope}{len(subject)}:{subject}".encode()).hexdigest()
