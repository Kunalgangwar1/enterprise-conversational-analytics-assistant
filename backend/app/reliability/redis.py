"""Construction helpers for bounded synchronous Redis clients."""

from redis import BlockingConnectionPool, Redis


def create_redis_client(
    redis_url: str,
    *,
    connect_timeout_seconds: float,
    socket_timeout_seconds: float,
    pool_timeout_seconds: float,
    max_connections: int,
) -> Redis:
    """Create a client whose connect, read, and pool waits are all finite."""

    pool = BlockingConnectionPool.from_url(
        redis_url,
        decode_responses=True,
        socket_connect_timeout=connect_timeout_seconds,
        socket_timeout=socket_timeout_seconds,
        max_connections=max_connections,
        timeout=pool_timeout_seconds,
    )
    return Redis.from_pool(pool)
