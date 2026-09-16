# Local analytical database

## Architecture distinction

The documented source architecture uses **Databricks SQL**. This clean-room reconstruction uses
**PostgreSQL only as its local development analytical store**. PostgreSQL is not presented as the
original production database, and its SQL semantics are not identical to Databricks SQL. Phase 4
introduces a database-independent read-only query boundary while retaining PostgreSQL as the local
implementation.

Only deterministic synthetic healthcare records may be stored in this project database.

## Schema

| Table | Purpose | Main relationships |
| --- | --- | --- |
| `members` | Synthetic enrollment and demographic attributes | Referenced by encounters, claims, and appointments |
| `facilities` | Synthetic care-delivery locations | Referenced by providers, encounters, and appointments |
| `providers` | Synthetic clinicians and specialties | Belongs to a facility |
| `encounters` | Synthetic care interactions | Belongs to a member, provider, and facility |
| `claims` | Synthetic claim headers and exact monetary totals | Belongs to a member/provider and optionally an encounter |
| `claim_lines` | Synthetic procedures and exact line amounts | Belongs to a claim; line number is unique within the claim |
| `appointments` | Synthetic scheduled visits | Belongs to a member, provider, and facility |

Foreign keys preserve referential integrity. Database checks enforce controlled domain values,
non-negative monetary values, and `paid <= allowed <= submitted/billed` ordering.

## Configuration

Create separate local development and test databases. Copy the root `.env.example` to `.env` and
replace its placeholder usernames/passwords with local values:

```dotenv
DATABASE_URL=postgresql+psycopg://local_user:local_password@localhost:5432/enterprise_analytics
TEST_DATABASE_URL=postgresql+psycopg://local_test_user:local_test_password@localhost:5432/enterprise_analytics_test
```

Never commit `.env`. `DATABASE_URL` is used by Alembic and the seed command. Integration tests use
only `TEST_DATABASE_URL`, preventing them from modifying the normal development database.

Query execution has separate configuration:

```dotenv
QUERY_DATABASE_URL=postgresql+psycopg://eca_reader:local_reader_password@localhost:5432/enterprise_analytics
QUERY_TEST_DATABASE_URL=postgresql+psycopg://eca_test_reader:local_test_reader_password@localhost:5432/enterprise_analytics_test
QUERY_MAX_ROWS=500
QUERY_TIMEOUT_MS=5000
```

`QUERY_DATABASE_URL` is optional at application startup but mandatory when the internal query
executor is requested. It never falls back to `DATABASE_URL`. Use a SELECT-only role for query
execution. `QUERY_TEST_DATABASE_URL` is reserved for query-executor integration tests.

## Read-only query execution

Future agents will depend on the database-independent `QueryExecutor` contract rather than
SQLAlchemy, Psycopg, PostgreSQL, or Databricks directly. There is no public SQL execution endpoint
in Phase 4.

The PostgreSQL implementation applies defense in depth:

```text
sqlglot PostgreSQL AST validation
    ↓
SELECT-only PostgreSQL role
    ↓
READ ONLY database transaction
    ↓
LOCAL statement timeout
    ↓
bounded max_rows + 1 fetching
```

The AST policy permits one SELECT/query expression, including read-only CTEs and set operations.
It rejects DML, DDL, commands, `SELECT INTO`, locking SELECTs, multiple statements, and forbidden
operations nested inside CTEs. In sqlglot 30.x, `SELECT INTO` is represented by `Into`, row locks by
`Lock`, and `CALL`/`DO` by non-query command nodes. Function calls cannot be classified semantically
by syntax alone, which is one reason database permissions, read-only transactions, and timeouts
remain mandatory.

This boundary does not replace future NLP-to-SQL semantic validation, policy checks, scoring, or
domain-aware query review.

## Local read-only role

Role creation is environment-specific and must not be placed in Alembic. Run equivalent commands
as a local PostgreSQL administrator, replacing all example names and passwords as appropriate:

```sql
CREATE ROLE eca_app LOGIN PASSWORD 'replace_with_local_app_password';
CREATE ROLE eca_reader LOGIN PASSWORD 'replace_with_local_reader_password';

GRANT CONNECT ON DATABASE enterprise_analytics TO eca_reader;
GRANT USAGE ON SCHEMA public TO eca_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO eca_reader;

ALTER DEFAULT PRIVILEGES FOR ROLE eca_app IN SCHEMA public
GRANT SELECT ON TABLES TO eca_reader;
```

`eca_app` remains the schema owner used for migrations and seeding. `eca_reader` is used only for
analytical SELECT queries. Production roles and credentials belong to deployment infrastructure,
not application migrations or source control.

## Migrations

Alembic owns development schema changes; application code must not call
`Base.metadata.create_all()` for the development database. From `backend/`:

```bash
alembic upgrade head
alembic current
alembic current --check-heads
```

The URL is loaded from application settings. `alembic.ini` intentionally contains no credentials.
Alembic provides reviewable, repeatable schema evolution and deterministic constraint names.

## Synthetic data

Apply migrations first, then seed the development database:

```bash
python -m app.db.seed
```

Defaults generate 12 facilities, 80 providers, 500 members, 3,000 encounters, 2,500 claims,
approximately one to three lines per claim, and 1,500 appointments for 2024-01-01 through
2026-08-31. Use `--help` to see deterministic seed, count, and date options.

Seeding refuses to run when any target table contains data. For an intentional local-development
reset and reseed:

```bash
python -m app.db.seed --reset
```

`--reset` deletes synthetic rows in foreign-key-safe order and is rejected outside local,
development, dev, or test application environments.

## Tests

Run tests that require no database:

```bash
pytest -m "not integration"
```

After configuring an isolated `TEST_DATABASE_URL`, run PostgreSQL integration tests:

```bash
pytest -m integration
```

The integration suite verifies connectivity, applies migrations to the test database, checks the
tables, and executes a relational join inside a rolled-back transaction. Without
`TEST_DATABASE_URL`, the suite skips with an explicit reason.

After configuring `QUERY_TEST_DATABASE_URL` with a SELECT-only role, the same integration marker
also verifies query execution, CTEs, bounded results, schema queries, joins, statement timeout, and
database-level denial of a harmless `DELETE ... WHERE false` attempt.
