# ADR-006: Compose APIs through an application factory and typed mode contract

- Status: Accepted
- Date: 2026-09-14

## Context

The backend is gaining multiple APIs and will eventually have specialist routes. Registering every
route and embedding application behavior directly in `main.py` would become difficult to maintain
and test. Chat-mode strings duplicated between routes and future clients would also be prone to
drift.

## Decision

Use a FastAPI application factory, a central router-composition module, typed canonical chat-mode
configuration, an immutable mode registry, and thin route/service separation. Use a small shared
error envelope for controlled application errors while retaining FastAPI's standard request
validation.

Mode configuration describes a product contract only. It does not create agent implementations or
enable tool feature flags. This clean-room system exposes canonical modes without historical
aliases.

## Alternatives considered

- Keep all routes and behavior in `main.py`
- Create the complete `/chat` endpoint before orchestration exists
- Generate static welcome text with an LLM
- Duplicate chat-mode strings across routes and frontend code

## Consequences

Application composition is clearer, the factory and services can be tested independently, and mode
keys have one stable source. New route groups can be added without turning `main.py` into a routing
module. Actual conversational APIs, sessions, orchestration, and specialist implementations remain
intentionally deferred.
