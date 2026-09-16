# ADR-019: Deterministic AI Dashboard surface

## Status

Accepted for Phase 19.

## Context

The source architecture has a separate AI Dashboard surface that does not participate in
conversational intent routing. The clean-room reconstruction needs useful synthetic healthcare
analytics while preserving the existing chat boundaries and avoiding model-dependent arithmetic.

## Decision

- Implement Dashboard as the lazy-loaded `#/dashboard` React route, separate from `#/` Chat.
- Keep Dashboard outside `ChatMode`, Supervisor, and specialist orchestration.
- Use dedicated `/api/dashboards/*` endpoints backed by a focused `DashboardService`.
- Use fixed deterministic aggregate SQL and return aggregate analytics only.
- Reuse the existing parameterized, bounded, timed, read-only `QueryExecutor` and query credential.
- Derive default dates from available synthetic data rather than the machine clock.
- Reuse React, React Router, Recharts, the API client, and local state/hooks.
- Require no LLM or AWS configuration and run no forecast automatically.

## Alternatives considered

- Modeling Dashboard as another chat mode would conflate deterministic BI and intent routing.
- Generating every widget through an LLM or NLP-to-SQL would add cost and nondeterminism.
- Fetching raw records and aggregating in React would weaken privacy and database efficiency.
- Adding another chart library or frontend state framework would duplicate existing capability.
- Patient-level drilldowns would violate the Phase 19 aggregate-only boundary.
- Forecasting on page load would introduce unnecessary model and database work.

## Consequences

- The dashboard is predictable, low latency, testable, and works without model credentials.
- Chat state and dashboard filters remain independent.
- Fixed metrics and joins require code changes when the dashboard definition evolves.
- Dynamic and deeper natural-language analytics remain available through Chat.
- Exports, scheduled delivery, authentication, and production scaling remain later phases.
