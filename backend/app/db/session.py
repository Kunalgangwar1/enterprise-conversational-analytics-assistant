"""Synchronous SQLAlchemy engine and session configuration."""

from sqlalchemy import Engine, create_engine
from sqlalchemy.engine import URL
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


def create_database_engine(database_url: str | URL | None = None) -> Engine:
    """Create a PostgreSQL engine without opening a connection eagerly."""
    resolved_url = database_url or str(get_settings().database_url)
    return create_engine(resolved_url, pool_pre_ping=True)


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Create the application's synchronous session factory."""
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


engine = create_database_engine()
SessionLocal = create_session_factory(engine)
