# ADR-028: Bounded provider and infrastructure reliability

- Status: Accepted
- Date: 2026-09-17
- Completed: 2026-09-18 (Phase 28 Pass 3)

## Context

Gemini, Azure OpenAI, and their embedding endpoints can time out, rate-limit, lose connectivity, or
return transient server failures. Provider SDK retry behavior differed and could obscure the actual
attempt budget. Reliability must improve without retrying deterministic failures, leaking content,
silently changing providers, or creating retry storms.

## Decision

Own retries in one provider-neutral synchronous policy above the adapters and disable SDK-internal
retries. Configure finite connect, request/read, and logical-operation budgets. Retry only normalized
timeout, rate-limit, connection, and transient server categories. Use bounded exponential backoff,
jitter, `Retry-After`, attempts, cumulative delay, and operation time.

Add a small lock-protected per-client circuit breaker with closed, open, and half-open states.
Availability failure thresholds open the circuit; open calls fail fast; bounded half-open trials
close or reopen it. No distributed state is required in Pass 1.

Keep fallback disabled by default. Permit exactly one explicitly configured secondary LLM provider
only for transient/circuit failures. Do not fall back for authentication, deterministic requests,
validation, policy rejection, or programming errors. Do not fall back between embedding providers
because embedding/index compatibility is model-specific.

Reuse Phase 27 metrics and tracing with fixed provider/operation/reason dimensions. Never capture
prompt, response, credentials, identities, SQL, retrieval content, or raw provider messages. Close
constructed provider resources during application shutdown.

### Pass 2: internal dependencies and degradation

Configure PostgreSQL engines with stale-connection pre-ping, finite connect and pool acquisition
timeouts, and bounded size/overflow. Preserve read-only transactions, statement timeout, row cap,
read-role isolation, and SQL validation. Do not retry an analytical query: once execution starts,
completion and snapshot semantics may be uncertain. Map connection/pool/permission outages to a
sanitized 503 and statement timeout to 504; transaction contexts roll back and release connections.

Configure Redis with finite connect, socket/read, and blocking-pool waits and bounded connections.
Keep optimistic session conflict retries finite, mapping exhaustion to 409. Preserve the Phase 22
decision that configured Redis never falls back to JSON. Preserve the Phase 23 fail-closed decision
that a Redis rate-limit outage rejects protected work with 503 rather than disabling the control.

Separate liveness from readiness. Liveness checks only the API process. Readiness probes PostgreSQL
and configured Redis dependencies with their existing bounds, returns aggregate status only, and
never calls an LLM or embedding provider. During shutdown, close database/Redis/provider resources
and bounded telemetry in an isolated best-effort sequence. Features that have no dependency on an
unavailable provider may continue; dependent features fail explicitly and never fabricate output.

Add bounded `db.unavailable`, `db.pool_timeout`, `db.statement_timeout`, `redis.unavailable`,
`session.conflict_exhausted`, and `readiness.failed` metrics without DSNs, SQL, Redis keys, identity,
or raw errors.

### Pass 3: failure validation and recovery

Validate the complete behavior through focused, network-free failure injection rather than a broad
regression or chaos run. The matrix includes provider timeout/429/503/open circuit, embedding
timeout, PostgreSQL unavailable/statement timeout/pool exhaustion, Redis outage/session conflict,
rate-limit storage failure, unavailable telemetry export, and invalid/expired OIDC authentication.

Keep one retry owner per dependency path. Provider SDK retries remain disabled and only the
application provider policy retries; orchestration does not replay calls. A configured fallback is
one hop with an independently bounded policy. PostgreSQL execution, Redis transport, OIDC claims,
and telemetry export are not retried by that policy. Derive the provider worst-case duration from
attempt timeout, attempt count, cumulative backoff, and the logical operation cap instead of using
brittle wall-clock tests.

Recovery uses existing client behavior: circuit half-open trials, Redis reconnect on a later
operation, and SQLAlchemy pre-ping/new connection acquisition. None requires application restart.
Telemetry initialization failure is the explicit exception: application work continues, but
exporter initialization waits for process restart/redeployment.

An open circuit is a provider-neutral failure, so API boundaries explicitly map it to the same
sanitized 503 contract as an exhausted provider request. Deterministic routes that do not construct
an LLM continue during an LLM outage; dependency-backed routes fail rather than fabricate output.

## Alternatives considered

- SDK-native retries only: rejected because policies differ and can nest across providers.
- Retry every exception: rejected because deterministic failures waste quota and amplify load.
- Unbounded exponential backoff: rejected because requests need predictable upper bounds.
- Automatic Gemini/Azure failover: rejected because it changes cost, data routing, and behavior
  without operator intent.
- Distributed circuit-breaker state: deferred as unnecessary complexity for the current process
  model.
- Automatic SQL replay: rejected because connection loss after execution begins has ambiguous
  completion and a repeat can observe a different snapshot.
- Redis-to-JSON or Redis-to-memory failover: rejected because it creates divergent state and can
  bypass shared security controls.
- Provider checks in readiness: rejected because external AI outages should not remove unrelated
  deterministic functionality from service.
- Large resilience dependency: rejected in favor of small testable internal primitives.
- Broad local chaos suite: rejected for this phase; focused failure injection and one optional,
  non-destructive Compose exercise provide sufficient evidence without destabilizing developer data.
- Multi-region, default Multi-AZ, read replicas, cross-region backup, and Route 53 failover: deferred
  because they materially change AWS cost and architecture.

## Consequences

Attempts, delays, state transitions, and fallback are explicit and testable. Transient failures can
take longer before surfacing, but configured budgets cap that delay. Per-process circuits can differ
between replicas. Synchronous SDK calls cannot be forcibly interrupted safely; finite transport
timeouts and pre-attempt operation-budget checks provide the implemented bound. Internal dependency
failures now have stable conflict/unavailable/timeout contracts, while conservative default pool
sizes deliberately remain untuned until Phase 29. Phase 28 implementation is complete. Live AWS
reliability validation remains deferred until the final AWS deployment, and HA/multi-region/DR are
not implied by this decision.
