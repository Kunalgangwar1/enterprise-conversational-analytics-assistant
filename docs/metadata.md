# Metadata and semantic schema

Phase 5 introduces an internal metadata layer for future natural-language-to-SQL work. It combines
database facts with curated business meaning without querying row data or exposing metadata over
HTTP.

## Two sources of truth

PostgreSQL is authoritative for physical metadata: table and column names, SQL types, nullability,
primary keys, foreign keys, and unique constraints. `SchemaIntrospector` reads these facts through
SQLAlchemy Inspector using the schema-owner `DATABASE_URL`. It is restricted to the seven
application tables and does not inspect system tables or sample values.

The version-controlled YAML files under `backend/config/metadata/` are authoritative for semantic
metadata: domain and table descriptions, table grain, aliases, controlled value hints, column
descriptions, and analytical notes. SQL types and constraints intentionally do not appear in YAML.

`MetadataRegistry` validates and merges both sources:

```text
PostgreSQL
    ↓
Metadata Introspection
    +
Semantic Catalog
    ↓
Metadata Registry
```

## Domains and table grain

The catalog defines five generic synthetic-healthcare domains:

| Domain | Tables |
| --- | --- |
| `member` | `members` |
| `provider_network` | `providers`, `facilities` |
| `clinical_encounters` | `encounters` |
| `claims` | `claims`, `claim_lines` |
| `scheduling` | `appointments` |

Grain states what one row represents. It is especially important for claims analysis: `claims` is
claim-level, while `claim_lines` is service-line-level. Joining them can duplicate claim-level
amounts unless an aggregation deliberately preserves the intended grain.

Aliases make common business wording explicit. Value hints document only controlled synthetic
categories already enforced by the Phase 3 schema, such as claim status, payer type, specialty,
facility type, encounter type, and appointment status. The refresh never samples names, contact
details, identifiers, dates of birth, or any other row values.

## Relationships and drift validation

Relationships are derived from physical foreign keys rather than copied into semantic YAML. The
registry checks that every semantic table and column exists, every present application table has
semantic coverage, domain mappings agree in both YAML files, and every relationship resolves to
known source and target columns. A mismatch raises `MetadataValidationError`; it is never silently
dropped.

The deterministic context builder accepts explicit table names and emits only those tables, their
physical attributes, their semantic descriptions, and their direct outgoing relationships. Sending
an entire database schema blindly to a model creates unnecessary context, ambiguity, cost, and
privacy risk. Future selection stages should narrow the catalog before building model context.

The documented `select_domains` and `select_tables` stages are **not implemented in Phase 5**.
There is no LLM, ranking, embedding, SQL generation, or metadata HTTP endpoint in this phase.

## Refreshing the generated snapshot

From `backend/`, with the schema-owner `DATABASE_URL` configured and the Phase 3 migration applied:

```bash
python -m app.metadata.refresh
```

The command reads the database schema and YAML catalogs, performs drift validation, then atomically
writes `backend/artifacts/metadata/schema_metadata.json`. The generated JSON is ignored by Git and
must not be edited as a source of truth. It contains schema metadata and a generation timestamp,
but no database URL, credentials, or row samples.
