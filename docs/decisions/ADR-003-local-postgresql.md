# ADR-003: PostgreSQL for the local analytical store

- Status: Accepted
- Date: 2026-09-13

## Context

The documented enterprise project uses Databricks SQL, but the clean-room reconstruction needs a
locally accessible relational database for schema, constraint, migration, and join exercises.

## Decision

Use PostgreSQL with SQLAlchemy 2.x and Psycopg 3 for local development. Manage schema evolution with
Alembic so changes are explicit, reviewable, repeatable, and separate from application startup.

## Alternatives considered

- Databricks from the beginning
- SQLite
- DuckDB

## Consequences

PostgreSQL offers strong relational and SQL fidelity, realistic constraints and joins, and
straightforward local use. It does not perfectly reproduce Databricks SQL semantics. A
database-independent query execution layer will be introduced in a later phase.
