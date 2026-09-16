# ADR-022: Redis-backed shared session state

## Status

Accepted.

## Context

The source reconstruction stores validated session JSON in local files. That is understandable and
appropriate for local learning, but process-local locking cannot prevent lost updates across
workers and local disks cannot provide one session view across hosts. Phase 21 also made session
ownership security-sensitive by binding state to authenticated subject, browser, and tab.

## Decision

- Preserve `JsonFileSessionStore` as the default, source-described backend.
- Add Redis as a clearly identified clean-room production extension selected by environment.
- Use official synchronous redis-py because the existing session call graph is synchronous.
- Reuse the existing SHA-256 subject/browser/tab identity digest; never expose raw identity in keys.
- Store a strict Pydantic-validated JSON envelope with schema version `1`; never use pickle.
- Reuse `SESSION_MAX_AGE_SECONDS` for Redis TTL and refresh it on every successful write.
- Move read/modify/write atomicity into `SessionStore.update`.
- Implement Redis mutations with bounded `WATCH`/`MULTI`/`EXEC` optimistic transactions.
- Return sanitized 409 responses after retry exhaustion and sanitized 503 responses on outages.
- Never fall back from Redis to local files.
- Create no Redis connection at import time and close the client during application shutdown.

## Rejected alternatives

- Keeping local files for multi-worker production
- A process lock presented as cross-process coordination
- Last-write-wins Redis `GET` followed by `SET`
- Distributed locks with leases for these short deterministic mutations
- Pickle or an unversioned payload
- Raw user, browser, or tab identifiers in Redis keys
- Automatic file fallback during Redis outages
- Adding an asynchronous Redis stack while the consuming call graph remains synchronous

## Consequences

Multiple replicas observe the same pending SQL, token mapping, selected mode, and history without
silently losing concurrent turns. Session availability now depends on Redis when that backend is
selected, and callers may need to retry a conflict. Existing JSON users retain their default local
workflow. Version changes require an explicit envelope migration strategy rather than accidental
best-effort parsing. Normal test runs remain infrastructure-free through a deterministic Redis test
double; a real Redis smoke check is optional and operational only.
