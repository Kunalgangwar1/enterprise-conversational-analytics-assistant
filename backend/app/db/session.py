"""Synchronous SQLAlchemy engine and session configuration."""

from sqlalchemy import Engine, create_engine
from sqlalchemy.engine import URL
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings, get_settings


def database_engine_options(settings: Settings) -> dict[str, object]:
    """Return conservative, bounded PostgreSQL pool and connection options."""

    return {
        "pool_pre_ping": True,
        "pool_size": settings.database_pool_size,
        "max_overflow": settings.database_max_overflow,
        "pool_timeout": settings.database_pool_timeout_seconds,
        "pool_recycle": settings.database_pool_recycle_seconds,
        "connect_args": {"connect_timeout": settings.database_connect_timeout_seconds},
    }


def create_database_engine(
    database_url: str | URL | None = None,
    *,
    settings: Settings | None = None,
) -> Engine:
    """Create a PostgreSQL engine with stale-checking and finite acquisition bounds."""

    resolved_settings = settings or get_settings()
    resolved_url = database_url or str(resolved_settings.database_url)
    return create_engine(resolved_url, **database_engine_options(resolved_settings))


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Create the application's synchronous session factory."""
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


engine = create_database_engine()
SessionLocal = create_session_factory(engine)
