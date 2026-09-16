# ADR-004: Safe query execution boundary

- Status: Accepted
- Date: 2026-09-14

## Context

Future LLM-generated SQL must not execute directly through SQLAlchemy or with database-owner
credentials. The documented source architecture ultimately targets Databricks SQL, while the local
reconstruction currently uses PostgreSQL.

## Decision

Introduce a database-independent `QueryExecutor` contract with a PostgreSQL implementation. Require
a separate SELECT-only connection, SQL AST validation, a read-only transaction, a local statement
timeout, bounded fetching, and sanitized errors. Keep a public execute-SQL API deferred.

## Alternatives considered

- Letting agents use SQLAlchemy directly
- Application-side string or regular-expression checks only
- Using the `eca_app` schema-owner account for all queries
- Exposing an execute-SQL HTTP endpoint immediately

## Consequences

The design provides stronger isolation and a clean seam for a future Databricks executor. It adds
a separate credential and role-management requirement. Parser safety is not semantic correctness,
so later NLP-to-SQL validation remains necessary.
