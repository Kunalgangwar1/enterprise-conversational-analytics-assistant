# ADR-007: Isolate typed session state by browser and tab

- Status: Accepted
- Date: 2026-09-14

## Context

Conversational follow-ups and independently selected modes require state across HTTP requests.
Sharing one browser-level session across all tabs would let concurrent conversations overwrite one
another, while putting the full state in a cookie would expose implementation details and increase
client payloads.

## Decision

Use an opaque UUID4 browser-session cookie together with a validated `X-Tab-Id` header to identify a
logical conversation. Persist typed Pydantic state as JSON behind a `SessionStore` abstraction. Use
a SHA-256-derived filename, atomic same-directory replacement, and a process-local lock. Reset only
the current tab's conversational fields and preserve its selected canonical mode.

`token_mapping_history` remains request-scoped, and `custom_context` will be supplied fresh with a
future chat request. Neither is durable session state.

## Alternatives considered

- Keep all state in the client
- Store the complete session payload in the cookie
- Introduce PostgreSQL-backed sessions immediately
- Introduce Redis immediately
- Share one server session across every tab in a browser

## Consequences

The implementation closely follows the documented reconstruction architecture, keeps sensitive
payloads out of cookies, supports local inspection, and isolates browser tabs. Local JSON storage
does not safely support horizontal multi-instance deployment, and its process lock does not provide
distributed coordination. A production shared-state implementation can later replace the store
without changing session-service behavior.
