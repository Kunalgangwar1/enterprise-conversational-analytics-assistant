"""Construction and process-level caching for the query executor."""

from functools import lru_cache

from sqlalchemy import create_engine

from app.core.config import Settings, get_settings
from app.db.query.base import QueryExecutor
from app.db.query.exceptions import QueryConfigurationError
from app.db.query.postgres import PostgresQueryExecutor


def build_query_executor(settings: Settings) -> PostgresQueryExecutor:
    """Build a dedicated PostgreSQL executor from explicit query settings."""
    if settings.query_database_url is None:
        raise QueryConfigurationError(
            "QUERY_DATABASE_URL is required before analytical queries can be executed."
        )

    query_engine = create_engine(str(settings.query_database_url), pool_pre_ping=True)
    return PostgresQueryExecutor(
        query_engine,
        max_rows=settings.query_max_rows,
        timeout_ms=settings.query_timeout_ms,
    )


@lru_cache(maxsize=1)
def get_query_executor() -> QueryExecutor:
    """Return the cached, explicitly configured analytical query executor."""
    return build_query_executor(get_settings())
