# ADR-009: Add deterministic privacy preprocessing before LLM workflows

- Status: Accepted
- Date: 2026-09-14

## Context

User text may contain healthcare or business identifiers and generic PII before it reaches future
LLM-backed components. The source architecture places privacy processing before supervisor routing
and reverses business-identifier mappings only after a response is produced. Mapping values are
themselves sensitive and should have the shortest useful lifetime.

## Decision

Introduce an internal deterministic `PrivacyProcessor` before the future LLM and supervisor.
Reversible Phase 3 business identifiers are replaced with collision-resistant, request-scoped
`Txxx` tokens. Conservative email and formatted US phone patterns are irreversibly replaced with
category placeholders. A separate `ResponseUnmasker` restores only exact standalone tokens in the
current request mapping.

The package remains independent of HTTP routes, session persistence, PostgreSQL, query execution,
and provider SDKs. It emits no raw prompt or mapping logs. `token_mapping_history` remains absent
from durable session state; a future chat service may assign the latest mapping to the existing
`last_token_mapping` field.

## Alternatives considered

- Send original text directly to the LLM
- Redact every detected value irreversibly
- Keep one global token map
- Query the analytics database for matching identities
- Introduce an external DLP or NLP platform immediately

## Consequences

- LLM-backed components receive less sensitive input for the supported patterns.
- Business identifier semantics can be restored in user-facing responses.
- Request-local allocation and deterministic patterns are straightforward to test.
- Token mappings remain sensitive and require careful handling by future orchestration.
- Generic free-text PHI recognition is intentionally incomplete.
- Dates and names require contextual approaches outside this baseline.
- Production privacy controls may require stronger dedicated services.
