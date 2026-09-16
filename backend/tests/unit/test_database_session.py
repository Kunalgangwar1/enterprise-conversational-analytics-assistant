"""Unit tests for database engine configuration."""

from app.db.session import create_database_engine


def test_database_engine_uses_psycopg_driver_without_connecting() -> None:
    engine = create_database_engine("postgresql+psycopg://synthetic_user@localhost/synthetic_db")

    assert engine.url.drivername == "postgresql+psycopg"
    assert engine.pool._pre_ping is True
    engine.dispose()
