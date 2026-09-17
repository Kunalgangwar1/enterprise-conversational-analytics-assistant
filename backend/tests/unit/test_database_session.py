"""Unit tests for bounded database engine configuration."""

from unittest.mock import MagicMock, patch

from app.core.config import Settings
from app.db.session import create_database_engine


def test_engine_enables_stale_connection_recovery_and_bounded_pool() -> None:
    settings = Settings(
        _env_file=None,
        app_env="test",
        database_pool_size=3,
        database_max_overflow=2,
        database_pool_timeout_seconds=1.5,
        database_connect_timeout_seconds=4,
    )
    engine = create_database_engine(
        "postgresql+psycopg://synthetic_user@localhost/synthetic_db",
        settings=settings,
    )

    assert engine.url.drivername == "postgresql+psycopg"
    assert engine.pool._pre_ping is True
    assert engine.pool.size() == 3
    assert engine.pool._max_overflow == 2
    assert engine.pool._timeout == 1.5
    engine.dispose()


def test_database_connect_timeout_is_passed_without_opening_connection() -> None:
    settings = Settings(
        _env_file=None,
        app_env="test",
        database_connect_timeout_seconds=4,
    )
    sentinel = MagicMock()
    with patch("app.db.session.create_engine", return_value=sentinel) as constructor:
        result = create_database_engine(
            "postgresql+psycopg://synthetic_user@localhost/synthetic_db",
            settings=settings,
        )

    assert result is sentinel
    assert constructor.call_args.kwargs["pool_pre_ping"] is True
    assert constructor.call_args.kwargs["pool_timeout"] == 5.0
    assert constructor.call_args.kwargs["connect_args"] == {"connect_timeout": 4}
