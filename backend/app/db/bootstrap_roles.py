"""Idempotent PostgreSQL role bootstrap for managed RDS deployments."""

from __future__ import annotations

import os
from dataclasses import dataclass

import psycopg
from psycopg import sql


@dataclass(frozen=True)
class DatabaseBootstrapSettings:
    """Administrative connection and least-privilege application role settings."""

    host: str
    port: int
    database: str
    admin_username: str
    admin_password: str
    app_username: str
    app_password: str
    reader_username: str
    reader_password: str
    ssl_root_cert: str

    @classmethod
    def from_environment(cls) -> DatabaseBootstrapSettings:
        required = {
            name: os.environ.get(name, "").strip()
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
            )
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise ValueError(f"Missing database bootstrap settings: {', '.join(missing)}")
        return cls(
            host=required["DB_BOOTSTRAP_HOST"],
            port=int(os.environ.get("DB_BOOTSTRAP_PORT", "5432")),
            database=required["DB_BOOTSTRAP_DATABASE"],
            admin_username=required["DB_BOOTSTRAP_ADMIN_USERNAME"],
            admin_password=required["DB_BOOTSTRAP_ADMIN_PASSWORD"],
            app_username=required["POSTGRES_APP_USER"],
            app_password=required["POSTGRES_APP_PASSWORD"],
            reader_username=required["POSTGRES_READER_USER"],
            reader_password=required["POSTGRES_READER_PASSWORD"],
            ssl_root_cert=required["DB_SSLROOTCERT"],
        )


def bootstrap_database_roles(
    connection: psycopg.Connection,
    settings: DatabaseBootstrapSettings,
) -> None:
    """Create or rotate application roles and reapply their grants safely."""

    with connection.cursor() as cursor:
        for role_name, password in (
            (settings.app_username, settings.app_password),
            (settings.reader_username, settings.reader_password),
        ):
            cursor.execute("SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = %s", (role_name,))
            if cursor.fetchone() is None:
                cursor.execute(
                    sql.SQL("CREATE ROLE {} LOGIN PASSWORD %s").format(sql.Identifier(role_name)),
                    (password,),
                )
            cursor.execute(
                sql.SQL("ALTER ROLE {} LOGIN PASSWORD %s").format(sql.Identifier(role_name)),
                (password,),
            )

        cursor.execute(
            sql.SQL("ALTER DATABASE {} OWNER TO {}").format(
                sql.Identifier(settings.database),
                sql.Identifier(settings.app_username),
            )
        )
        cursor.execute(
            sql.SQL("ALTER SCHEMA public OWNER TO {}").format(sql.Identifier(settings.app_username))
        )
        cursor.execute(
            sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                sql.Identifier(settings.database),
                sql.Identifier(settings.reader_username),
            )
        )
        cursor.execute(
            sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(
                sql.Identifier(settings.reader_username)
            )
        )
        cursor.execute(
            sql.SQL("GRANT SELECT ON ALL TABLES IN SCHEMA public TO {}").format(
                sql.Identifier(settings.reader_username)
            )
        )
        cursor.execute(
            sql.SQL(
                "ALTER DEFAULT PRIVILEGES FOR ROLE {} IN SCHEMA public GRANT SELECT ON TABLES TO {}"
            ).format(
                sql.Identifier(settings.app_username),
                sql.Identifier(settings.reader_username),
            )
        )


def main() -> None:
    """Connect with the RDS administrator only for the bounded bootstrap operation."""

    settings = DatabaseBootstrapSettings.from_environment()
    with psycopg.connect(
        host=settings.host,
        port=settings.port,
        dbname=settings.database,
        user=settings.admin_username,
        password=settings.admin_password,
        sslmode="verify-full",
        sslrootcert=settings.ssl_root_cert,
        connect_timeout=10,
        autocommit=True,
    ) as connection:
        bootstrap_database_roles(connection, settings)
    print("PostgreSQL application and read-only roles are configured.")


if __name__ == "__main__":
    main()
