"""Focused tests for the managed PostgreSQL role bootstrap."""

from collections.abc import Iterator

import pytest

from app.db.bootstrap_roles import DatabaseBootstrapSettings, bootstrap_database_roles


class FakeCursor:
    def __init__(self, role_exists: bool) -> None:
        self.role_exists = role_exists
        self.executions: list[tuple[object, object | None]] = []

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def execute(self, query: object, parameters: object | None = None) -> None:
        self.executions.append((query, parameters))

    def fetchone(self) -> tuple[int] | None:
        return (1,) if self.role_exists else None


class FakeConnection:
    def __init__(self, role_exists: bool) -> None:
        self.cursor_instance = FakeCursor(role_exists)

    def cursor(self) -> FakeCursor:
        return self.cursor_instance


@pytest.fixture
def settings() -> DatabaseBootstrapSettings:
    return DatabaseBootstrapSettings(
        host="db.example.invalid",
        port=5432,
        database="enterprise_analytics",
        admin_username="admin",
        admin_password="admin-secret",
        app_username="eca_app",
        app_password="app-secret",
        reader_username="eca_reader",
        reader_password="reader-secret",
        ssl_root_cert="/etc/ssl/certs/aws-rds-global-bundle.pem",
    )


def _query_texts(connection: FakeConnection) -> Iterator[str]:
    return (str(query) for query, _parameters in connection.cursor_instance.executions)


def test_bootstrap_creates_missing_roles_and_applies_least_privilege_grants(settings) -> None:
    connection = FakeConnection(role_exists=False)

    bootstrap_database_roles(connection, settings)  # type: ignore[arg-type]

    statements = list(_query_texts(connection))
    assert sum("CREATE ROLE" in statement for statement in statements) == 2
    assert any("GRANT SELECT ON ALL TABLES" in statement for statement in statements)
    assert any("ALTER DEFAULT PRIVILEGES" in statement for statement in statements)
    assert all("admin-secret" not in statement for statement in statements)
    assert all("app-secret" not in statement for statement in statements)
    assert all("reader-secret" not in statement for statement in statements)


def test_bootstrap_is_idempotent_when_roles_already_exist(settings) -> None:
    connection = FakeConnection(role_exists=True)

    bootstrap_database_roles(connection, settings)  # type: ignore[arg-type]

    statements = list(_query_texts(connection))
    assert not any("CREATE ROLE" in statement for statement in statements)
    assert sum("ALTER ROLE" in statement for statement in statements) == 2


def test_environment_loader_rejects_missing_secrets(monkeypatch) -> None:
    for name in (
        "DB_BOOTSTRAP_HOST",
        "DB_BOOTSTRAP_DATABASE",
        "DB_BOOTSTRAP_ADMIN_USERNAME",
        "DB_BOOTSTRAP_ADMIN_PASSWORD",
        "POSTGRES_APP_USER",
        "POSTGRES_APP_PASSWORD",
        "POSTGRES_READER_USER",
        "POSTGRES_READER_PASSWORD",
        "DB_SSLROOTCERT",
    ):
        monkeypatch.delenv(name, raising=False)

    with pytest.raises(ValueError, match="Missing database bootstrap settings"):
        DatabaseBootstrapSettings.from_environment()
