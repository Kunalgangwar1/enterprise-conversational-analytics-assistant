# ADR-018: One UI and thin chat orchestration

## Status

Accepted for Phase 18.

## Context

The backend specialists, privacy boundary, routing supervisor, session contract, SQL generation and
execution paths, advanced reasoning, and forecasting already exist. The reconstruction needs one
conversational application surface without moving routing or business rules into the browser.

## Decision

- Add a thin application-level `ChatOrchestrator` behind `POST /chat`.
- Read the selected top-level mode from server-side session state and privacy-process current-turn
  message and context before routing or specialist use.
- Reuse `SupervisorMultiAgent`, the applicable `ReasoningPromotionPolicy`, and the existing
  specialist implementations through a typed specialist registry.
- Preserve standard SQL's two-step contract: generate and store accepted privacy-safe SQL, then
  execute it only after a separate client request to `/chat/execute-sql`.
- Provide one React/TypeScript/webpack interface using `HashRouter` and typed specialist responses.
- Isolate browser tabs with the existing cookie plus `X-Tab-Id` session identity.
- Keep routing, privacy, authorization-relevant decisions, and analytical business logic on the
  backend. The frontend renders typed results and does not expose agent reasoning internals.

## Alternatives considered

- Calling every specialist endpoint directly from React would duplicate orchestration concerns.
- Duplicating routing in the frontend would create conflicting policy and make it client-controlled.
- Automatically executing every generated SQL query would remove explicit user control.
- Accepting editable arbitrary SQL would bypass the server-owned validation and session boundary.
- Rebuilding the frontend with another framework would depart from the documented source shape.
- Exposing decomposition, reflection, or chain-of-thought would violate the response boundary.

## Consequences

- Users have one consistent surface while the backend remains authoritative.
- The frontend remains relatively thin and specialist responses stay explicit and testable.
- Standard SQL retains review and explicit execution control.
- The webpack and routing foundation can support a later Dashboard without implementing it now.
- Group Access remains controlled-unavailable until a real specialist exists.
- Complete production authentication and RBAC remain Phase 21 concerns.
