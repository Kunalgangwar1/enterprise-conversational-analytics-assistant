# ADR-011: Model standard NLP-to-SQL generation as a LangGraph

- Status: Accepted
- Date: 2026-09-14

## Context

SQL generation requires explicit schema-resolution stages and will later require conditional
validation and one controlled rewrite path. Sending the entire schema in one question-to-SQL call
would increase context size, obscure stage-specific failures, and make later validation edges
harder to inspect.

The documented source architecture uses Databricks SQL, while this clean-room reconstruction uses
PostgreSQL as its intentional local database substitute.

## Decision

Use LangGraph `StateGraph` for the linear Phase 11 workflow:

```text
refresh_metadata -> select_domains -> select_tables -> build_metadata -> generate_sql
```

Use `TypedDict` for mutable graph state, Pydantic for structured LLM outputs, the existing
`MetadataRegistry` for schema and semantics, and the provider-neutral `LLMClient` for all three
model calls. Generate PostgreSQL syntax and stop after returning unvalidated, unexecuted SQL.

## Alternatives considered

- Use one prompt containing the entire schema
- Call the model directly from question to SQL
- Implement only a procedural service without an inspectable graph
- Use a LangChain SQL agent toolkit
- Execute SQL immediately after generation

## Consequences

- The pipeline and stage boundaries are explicit and inspectable.
- Domain-first selection reduces schema context.
- Individual stages support deterministic fake-client testing.
- The graph is ready for Phase 12 validation and rewrite edges.
- A normal generation makes three LLM calls and therefore adds latency.
- Metadata quality directly affects selection and generation quality.
- Generated SQL remains untrusted until Phase 12 validates it.
- SQL execution remains a separate Phase 13 responsibility.
