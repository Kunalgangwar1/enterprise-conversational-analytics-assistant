# ADR-005: Combine database introspection with curated semantic metadata

- Status: Accepted
- Date: 2026-09-14

## Context

NLP-to-SQL needs more meaning than raw table and column names provide. Manually duplicating the
physical schema alongside business descriptions is error-prone and can become stale as migrations
change the database.

## Decision

Use SQLAlchemy Inspector to derive physical metadata from PostgreSQL and combine it with curated,
version-controlled YAML business semantics in a validated `MetadataRegistry`. PostgreSQL remains
authoritative for physical structure; YAML remains authoritative for descriptions, aliases, grain,
controlled value hints, and analytical notes. Fail registry construction when the sources drift.

## Alternatives considered

- Hardcode schema strings in prompts
- Give the entire PostgreSQL schema directly to every LLM request
- Manually maintain physical and semantic metadata together
- Introduce embeddings or vector retrieval immediately

## Consequences

Business meaning is explicit and reviewable, physical structure remains database-driven, and schema
drift can be detected before future model use. Semantic metadata still requires deliberate
maintenance when business meaning changes. Domain and table selection remain later-phase concerns;
Phase 5 performs no LLM selection, retrieval, or SQL generation.
