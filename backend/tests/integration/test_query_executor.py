"""Integration tests for the dedicated PostgreSQL read-only query role."""

from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, create_engine
from sqlalchemy.exc import DBAPIError, SQLAlchemyError

from app.core.config import get_settings
from app.db.query.exceptions import QueryTimeoutError
from app.db.query.postgres import PostgresQueryExecutor

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def query_engine() -> Iterator[Engine]:
    settings = get_settings()
    if settings.query_test_database_url is None:
        pytest.skip(
            "QUERY_TEST_DATABASE_URL is not configured; read-only query integration tests skipped"
        )

    engine = create_engine(str(settings.query_test_database_url), pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            connection.exec_driver_sql("SELECT 1")
    except SQLAlchemyError:
        engine.dispose()
        pytest.fail("Could not connect to the isolated PostgreSQL QUERY_TEST_DATABASE_URL")

    yield engine
    engine.dispose()


@pytest.fixture(scope="module")
def query_executor(query_engine: Engine) -> PostgresQueryExecutor:
    return PostgresQueryExecutor(query_engine, max_rows=500, timeout_ms=5_000)


def _members_table_exists(executor: PostgresQueryExecutor) -> bool:
    result = executor.execute("SELECT to_regclass('public.members') AS table_name")
    return result.rows[0]["table_name"] is not None


def test_read_only_select_and_cte_work(query_executor: PostgresQueryExecutor) -> None:
    select_result = query_executor.execute("SELECT 1 AS value")
    cte_result = query_executor.execute(
        "WITH cte_data AS (SELECT 2 AS value) SELECT * FROM cte_data"
    )

    assert select_result.rows == [{"value": 1}]
    assert cte_result.rows == [{"value": 2}]


def test_maximum_rows_are_truncated(query_engine: Engine) -> None:
    executor = PostgresQueryExecutor(query_engine, max_rows=3, timeout_ms=5_000)

    result = executor.execute("SELECT generate_series(1, 10) AS n")

    assert result.rows == [{"n": 1}, {"n": 2}, {"n": 3}]
    assert result.row_count == 3
    assert result.truncated is True


def test_phase_three_schema_queries_and_join(query_executor: PostgresQueryExecutor) -> None:
    if not _members_table_exists(query_executor):
        pytest.skip("Phase 3 schema is not present in QUERY_TEST_DATABASE_URL")

    member_count = query_executor.execute("SELECT COUNT(*) AS member_count FROM members")
    join_count = query_executor.execute(
        "SELECT COUNT(*) AS encounter_count "
        "FROM encounters e "
        "JOIN members m ON m.id = e.member_id "
        "JOIN providers p ON p.id = e.provider_id"
    )

    assert member_count.row_count == 1
    assert isinstance(member_count.rows[0]["member_count"], int)
    assert join_count.row_count == 1
    assert isinstance(join_count.rows[0]["encounter_count"], int)


def test_statement_timeout_is_enforced(query_engine: Engine) -> None:
    executor = PostgresQueryExecutor(query_engine, max_rows=1, timeout_ms=10)

    with pytest.raises(QueryTimeoutError):
        executor.execute("SELECT pg_sleep(0.1)")


def test_query_role_cannot_delete_even_with_no_op_condition(query_engine: Engine) -> None:
    executor = PostgresQueryExecutor(query_engine, max_rows=1, timeout_ms=5_000)
    if not _members_table_exists(executor):
        pytest.skip("Phase 3 schema is not present in QUERY_TEST_DATABASE_URL")

    try:
        with query_engine.connect() as connection, connection.begin():
            connection.exec_driver_sql("DELETE FROM claims WHERE false")
    except DBAPIError as exc:
        assert getattr(exc.orig, "sqlstate", None) == "42501"
    else:
        pytest.fail("QUERY_TEST_DATABASE_URL role unexpectedly has DELETE permission")
