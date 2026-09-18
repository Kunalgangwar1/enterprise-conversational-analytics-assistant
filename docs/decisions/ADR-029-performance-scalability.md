# ADR-029: Performance and scalability boundaries

- Status: Accepted
- Date: 2026-09-18

## Context

The completed application needed reproducible evidence about deterministic HTTP, SQL, Redis, and
frontend paths without spending provider tokens or pretending local throughput is AWS capacity.
Horizontal scaling also requires an explicit PostgreSQL connection budget and shared state.

## Decision

Use pinned Locust as a development-only tool with smoke, baseline, and manual stress profiles.
Performance chat uses a FakeLLM target; SQL and Redis paths remain real when the documented local
stack is used. Normalize request names, export machine-readable and human-readable artifacts, and
apply configurable local gates to failure rate, p95, and p99.

Keep all existing SQL safety and reliability limits. Add finite pool recycling and validate the
maximum ECS task/worker/engine pool demand against a declared connection budget. Provide optional
CPU and memory target tracking, disabled by default, with bounded capacity and cooldowns.

Apply only measured application changes: lazily load Recharts-backed SQL and forecast result UI and
split runtime/vendor chunks. Do not change retrieval, query semantics, indexes, or the already lean
multi-stage backend image without evidence.

## Consequences

Local and CI regressions are reviewable and provider-free. The conservative three-pool connection
multiplier reduces accidental RDS oversubscription but must be recalculated if engine ownership is
refactored. Frontend visualization code arrives after the corresponding result is requested. CI
smoke results are not production SLOs or capacity guarantees.

## Deferred

Live AWS load, autoscaling/draining validation, provider latency, production SLOs, RDS/Valkey sizing,
and cost/concurrency ceilings remain deployment-time work. No multi-region, DR, read-replica, or
broad HA architecture is introduced.
