"""Unit tests for explicit query-executor configuration."""

from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.db.query import factory as query_factory
from app.db.query.exceptions import QueryConfigurationError
from app.db.query.factory import build_query_executor


def test_query_database_url_is_required_without_owner_fallback() -> None:
    settings = Settings(
        _env_file=None,
        database_url="postgresql+psycopg://owner@localhost/owner_database",
        query_database_url=None,
    )

    with pytest.raises(QueryConfigurationError, match="QUERY_DATABASE_URL is required"):
        build_query_executor(settings)


@pytest.mark.parametrize("field_name", ["query_max_rows", "query_timeout_ms"])
def test_positive_query_limits_are_validated(field_name: str) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{field_name: 0})


def test_configured_executor_uses_query_url_and_is_cached(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(
        _env_file=None,
        database_url="postgresql+psycopg://owner@localhost/owner_database",
        query_database_url="postgresql+psycopg://reader@localhost/analytics_database",
        query_max_rows=7,
        query_timeout_ms=250,
    )
    engine = MagicMock()
    create_engine = MagicMock(return_value=engine)
    monkeypatch.setattr(query_factory, "get_settings", lambda: settings)
    monkeypatch.setattr(query_factory, "create_engine", create_engine)
    query_factory.get_query_executor.cache_clear()

    first_executor = query_factory.get_query_executor()
    second_executor = query_factory.get_query_executor()

    assert first_executor is second_executor
    create_engine.assert_called_once_with(str(settings.query_database_url), pool_pre_ping=True)
    query_factory.get_query_executor.cache_clear()
