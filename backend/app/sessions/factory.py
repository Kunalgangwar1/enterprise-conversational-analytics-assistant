"""Configuration-driven construction of the application session backend."""

from app.core.config import Settings
from app.sessions.json_store import JsonFileSessionStore
from app.sessions.redis_store import RedisSessionStore
from app.sessions.store import SessionStore


def build_session_store(settings: Settings) -> SessionStore:
    """Build exactly the configured backend without runtime fallback."""

    if settings.session_store_backend == "json":
        return JsonFileSessionStore(settings.artifacts_output_dir / "sessions")

    redis_url = settings.session_redis_url
    if redis_url is None:  # Defensive: Settings rejects this configuration first.
        raise ValueError("SESSION_REDIS_URL is required when SESSION_STORE_BACKEND=redis")
    return RedisSessionStore(
        redis_url.get_secret_value(),
        key_prefix=settings.session_redis_key_prefix,
        ttl_seconds=settings.session_max_age_seconds,
        max_update_retries=settings.session_redis_max_update_retries,
        connect_timeout_seconds=settings.redis_connect_timeout_seconds,
        socket_timeout_seconds=settings.redis_socket_timeout_seconds,
        pool_timeout_seconds=settings.redis_pool_timeout_seconds,
        max_connections=settings.redis_max_connections,
    )
