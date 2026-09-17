# Provider, infrastructure, and service reliability

Phase 28 Pass 1 adds bounded resilience around external AI provider reads. Pass 2 adds explicit,
bounded failure behavior for PostgreSQL, Redis, sessions, readiness, and application shutdown. It
does not add broad service retries, bulkheads, chaos testing, or Phase 29 performance tuning. Pass 3
validates the cross-layer failure contracts and records operational recovery procedures.

## Dependency reliability summary

| Dependency | Timeout | Retries | Circuit breaker | Fallback | Failure status | Recovery |
|---|---|---|---|---|---|---|
| Gemini/Azure LLM | 5s connect, 30s request, 90s logical operation | 2 retries / 3 total attempts for transient failures | Per-process, 5 failures, 30s cooldown, 1 half-open trial | Disabled by default; one explicit provider hop | 503 after exhaustion or open circuit | Next bounded call, or half-open trial after cooldown |
| Gemini/Azure embeddings | Same provider timeout and retry budgets | 2 retries / 3 total attempts for transient failures | Same per-client policy | None; model/index compatibility forbids it | 503 at embedding-backed API boundaries | Next bounded call, or half-open trial after cooldown |
| PostgreSQL | 5s connect, 5s pool wait, 5s default statement timeout | No SQL replay | None | None | 503 unavailable/pool/permission; 504 statement timeout | Pool pre-ping/new connection on a later request |
| Redis sessions | 2s connect, 2s socket, 2s pool wait | No transport retry; 5 bounded WATCH conflict attempts | None | No Redis-to-JSON fallback | 503 outage; 409 conflict exhaustion | Existing client reconnects on a later operation |
| Redis rate limiter | 2s connect, 2s socket, 2s pool wait | No application retry | None | No in-memory fallback | 503 fail-closed | Existing client reconnects on a later operation |
| OpenTelemetry exporter | 5s export/flush bound | No application retry | None | Telemetry becomes no-op/fail-open | Application response is unaffected | Later exports can recover; initialization failure requires process reinitialization |

Timeouts are defaults. Environment-backed settings may tighten or change them within validated
bounds. The logical provider upper bound is computed as the lower of the configured operation limit
and `(request timeout × total attempts) + maximum cumulative backoff`; tests validate the math
without slow wall-clock sleeps.

## Timeout philosophy

Provider calls must have finite transport and logical-operation bounds:

- `LLM_CONNECT_TIMEOUT_SECONDS=5` bounds connection establishment.
- `LLM_TIMEOUT_SECONDS=30` bounds one SDK request/read operation.
- `LLM_OPERATION_TIMEOUT_SECONDS=90` bounds whether another full attempt may begin.

Azure receives an explicit `httpx.Timeout` with separate connect and read/write/pool values. Gemini
receives the SDK request timeout plus a bounded HTTPX client default; its SDK applies the request
timeout to each generated request. Before retrying, the application requires enough operation
budget for another complete request timeout. This avoids infinite waits without using unsafe thread
termination. Provider SDK retries are disabled so retries never multiply invisibly.

## Retry matrix

| Failure | Retry? | Normalized category |
|---|---:|---|
| Connection/transport failure | Yes | `ProviderUnavailableError` |
| Request timeout / HTTP 408 | Yes | `ProviderTimeoutError` |
| HTTP 429 | Yes | `ProviderRateLimitError` |
| HTTP 500/502/503/504 | Yes | `ProviderUnavailableError` |
| Authentication/authorization | No | `ProviderAuthenticationError` |
| Deterministic HTTP 4xx | No | `ProviderRequestError` |
| Invalid structured output/content rejection | No | existing validation error |
| Unsupported provider/model or invalid settings | No | configuration/request error |
| Application/programming exception | No | original exception |

Only the existing read-like provider abstraction is retried. No business mutation is retried.
Gemini/Azure adapters retain their existing LLM/embedding-specific exception types, which now also
belong to the provider-neutral taxonomy. Raw provider bodies and exception messages are not exposed.

## Backoff, jitter, and retry budget

The default is three total attempts (`LLM_MAX_RETRIES=2`) with exponential delays beginning at
0.5 seconds, capped at 8 seconds per delay and 15 seconds total. Jitter is ±20%. `Retry-After` is
honored when available, while remaining bounded by the per-delay, total-delay, and operation
budgets. A single provider logical call therefore cannot create an unbounded attempt or sleep loop.

With explicit fallback enabled, the maximum is one bounded primary policy followed by one bounded
secondary policy. This is deliberate and visible rather than an implicit retry storm.

## Retry ownership and storm prevention

The application reliability policy is the single retry owner for LLM and embedding calls. Gemini is
configured for one SDK attempt and Azure OpenAI for `max_retries=0`, so SDK retries cannot multiply
the application attempt count. Chat orchestration and specialist layers do not replay provider
calls. Explicit fallback is one hop only: at most one bounded primary policy followed by one bounded
secondary policy.

PostgreSQL queries, Redis transport operations, OIDC validation, and telemetry export are not placed
under the provider retry policy. Redis WATCH conflicts have their own finite concurrency retry count;
that loop does not retry network outages. This keeps retry ownership local and auditable.

## Circuit breaker

Each constructed provider client owns a small process-local, lock-protected circuit breaker:

- closed: calls proceed; a successful/deterministic response clears availability failures;
- open: calls fail fast with `CircuitOpenError`;
- half-open: after the recovery timeout, a bounded number of trial calls may proceed.

Defaults are five failed logical calls, a 30-second recovery timeout, and one half-open trial.
Only exhausted transient failures count toward opening. Authentication, validation, request, and
programming errors do not. A failed half-open availability trial reopens the circuit; success closes
it. `LLM_CIRCUIT_BREAKER_ENABLED=false` disables state transitions without changing calls.

The breaker is intentionally not distributed. Separate processes and provider clients have separate
state.

## Explicit fallback

`LLM_FALLBACK_PROVIDER=none` is the default. Set it explicitly to `gemini` or `azure_openai`, and
configure that provider completely, to permit one fallback after timeout, rate-limit,
unavailability, or open-circuit failure. The fallback must differ from `LLM_PROVIDER`. Authentication,
deterministic request, validation, content-policy, and programming failures never trigger fallback.

Embedding calls use bounded retries and circuit breaking but do not switch embedding providers;
silently mixing embedding models would invalidate vector-index compatibility.

## Observability and privacy

The reliability layer adds the `provider.call` span and these bounded counters:

- `provider.retries`
- `provider.timeouts`
- `provider.unavailable`
- `provider.circuit_open`
- `provider.fallbacks`

Allowed dimensions are the configured provider, fixed operation (`generate`,
`generate_structured`, `embed_documents`, or `embed_query`), and a fixed reason code (`timeout`,
`rate_limited`, `unavailable`, or `circuit_open`). Spans record retry count and outcome. Prompts,
responses, API keys, user/session identities, provider bodies, and raw exception messages are never
attributes or metric dimensions.

## Configuration and shutdown

Settings validate timeout ordering, delay ordering, retry bounds, circuit limits, and distinct
fallback providers at startup/factory creation. Factories validate all required credentials,
endpoints, deployments, and models before returning a client. Constructed SDK resources register
for best-effort closure during FastAPI shutdown; wrappers also expose idempotent cascading `close()`
behavior for direct callers.

## Database failure policy

Application and analytical SQLAlchemy engines use `pool_pre_ping` to discard stale connections,
finite connection establishment and pool-acquisition timeouts, and bounded pool size/overflow.
Defaults are a five-second connect timeout, a five-second pool wait, five retained connections, and
five overflow connections. These are safety bounds, not throughput sizing.

Analytical execution remains a validated SELECT inside a read-only transaction with a PostgreSQL
statement timeout and application row cap. SQL execution is not retried: after execution begins,
transport failure can leave completion uncertain, and repeating even a SELECT can produce a result
from a different database snapshot. Pool pre-ping may replace a stale connection before the
transaction begins; this is connection validation, not query retry. Failed transaction contexts
roll back and release their connection.

| Database failure | Application result | HTTP result |
|---|---|---:|
| Connection refused, invalidated connection, shutdown, or capacity rejection | dependency unavailable | 503 |
| Pool acquisition timeout | dependency unavailable / pool timeout metric | 503 |
| PostgreSQL statement timeout | query timeout | 504 |
| Read-role permission failure | dependency unavailable with safe role message | 503 |
| Deterministic query execution error | generic safe execution error | 500 |

DSNs, raw SQL, driver messages, credentials, and database host details are never returned.

## Redis and session policy

Redis clients use finite connect, socket/read, and blocking-pool waits plus a bounded maximum
connection count. Defaults are two seconds for each timeout and 20 connections. Session
WATCH/MULTI/EXEC retries remain bounded by `SESSION_REDIS_MAX_UPDATE_RETRIES`; exhaustion produces
the stable `session_conflict` 409 response. Redis transport/pool failure produces a sanitized 503.

There is no runtime Redis-to-JSON fallback. When Redis is selected, an outage never creates
divergent process-local or file-backed session state. JSON remains an explicitly configured local
development backend only. The Redis rate-limit backend also fails closed: inability to make a
shared limiting decision returns `rate_limit_unavailable` (503) instead of allowing the request or
switching to the in-memory limiter.

## Liveness and readiness

`GET /api/health` is lightweight process liveness and performs no dependency or provider calls.
`GET /api/ready` probes the database and each configured Redis dependency. Every probe is bounded
by its transport/pool settings. Readiness never calls Gemini, Azure OpenAI, embeddings, or another
external LLM. A failure returns only aggregate `service_not_ready` (503); infrastructure addresses
and exception details remain private.

## Graceful shutdown

FastAPI lifespan cleanup closes lazily created analytical SQL and dashboard pools, the rate-limit
backend, the session backend, Pass 1 provider clients, the application database pool, and finally
flushes/shuts down Phase 27 telemetry. Cleanup is best effort and isolated so one close failure does
not prevent later resources from closing. Redis close and SQLAlchemy pool disposal are local pool
operations; telemetry export uses its configured finite timeout.

## Degradation matrix

| Unavailable dependency | Functionality that may continue | Functionality that fails explicitly |
|---|---|---|
| Gemini/Azure LLM | Deterministic Data Discovery and routes that do not construct an LLM | Routes that genuinely require that provider |
| Analytical PostgreSQL | Liveness and non-SQL deterministic features | SQL execution, dashboards, and database-dependent analytics |
| Required session Redis | Liveness | Stateful chat/session operations and readiness |
| Required rate-limit Redis | Liveness and unprotected inexpensive endpoints | Protected expensive operations fail closed; readiness fails |
| Telemetry exporter | Application work | Export only; telemetry remains fail-open as decided in Phase 27 |

No degraded path fabricates an answer or silently changes persistence/security backends.

## Validated failure classification

| Scenario | Retry? | Fallback? | HTTP outcome | Observable signal | User-safe? | Data consistency risk |
|---|---|---|---|---|---|---|
| LLM timeout | Transient policy only | Only when explicitly configured | 503 after exhaustion | `provider.timeouts`, `provider.retries` | Yes | No turn is persisted before completion |
| LLM HTTP 429 | Transient policy; bounded `Retry-After` | Only when explicitly configured | 503 after exhaustion | `provider.unavailable`, `provider.retries` with `rate_limited` | Yes | No additional application mutation |
| LLM HTTP 503 | Transient policy only | Only when explicitly configured | 503 after exhaustion | `provider.unavailable`, `provider.retries` | Yes | No additional application mutation |
| Open provider circuit | No provider attempt | Explicit one-hop fallback may run | 503 without healthy fallback | `provider.circuit_open`; `provider.fallbacks` when used | Yes | None |
| Embedding timeout | Transient policy only | Never | 503 after exhaustion | `provider.timeouts`, `provider.retries` | Yes | Index is not silently rebuilt with another model |
| PostgreSQL unavailable | No query replay | Never | 503 | `db.unavailable`; readiness failure when probed | Yes | Read-only transaction is released; result is not fabricated |
| PostgreSQL statement timeout | No | Never | 504 | `db.statement_timeout` | Yes | Transaction rolls back |
| PostgreSQL pool exhaustion | No | Never | 503 after bounded pool wait | `db.pool_timeout` | Yes | Query never acquires a connection |
| Redis unavailable | No transport retry | Never | 503 | `redis.unavailable`; readiness failure when required | Yes | No divergent JSON/local session is created |
| Redis session conflict exhaustion | Bounded WATCH retries only | Never | 409 | `session.conflict_exhausted` | Yes | Atomic transaction prevents lost update |
| Rate-limit Redis unavailable | No | Never | 503 fail-closed | `redis.unavailable`, `security.rate_limited_requests` | Yes | Protected work is not admitted without a decision |
| OTel exporter unavailable | No application retry | Telemetry no-op/fail-open | Business response unchanged | Sanitized operational warning; bounded shutdown | Yes | Application data path is unaffected |
| Invalid or expired OIDC token | No dependency retry | Never | 401 | `auth.authentication_failures` | Yes | Request is rejected before protected work/session mutation |

The automated failure scenarios use mocks/fakes and do not require provider credentials, internet,
AWS, or destructive database/cache manipulation.

## Operational recovery

- Provider circuit: after the cooldown, one bounded half-open trial is admitted. Success closes the
  circuit; a transient failure reopens it. No restart is required.
- Redis: redis-py reconnects through its bounded pool on the next operation. Session state remains in
  Redis; no local substitute is created. A successful later operation/readiness probe confirms
  recovery without restarting the application.
- PostgreSQL: SQLAlchemy pool pre-ping rejects stale connections and obtains a fresh connection under
  the connect/pool timeouts. A later request can succeed on the same executor after the database
  returns. Failed queries themselves are never replayed.
- OpenTelemetry: an already initialized exporter may recover on later exports. If initialization
  failed and observability was disabled for that process, restart/redeployment is required to
  initialize exporters again; application work remains available meanwhile.

## Local failure exercise

Run this only against the local Compose project with synthetic data. First confirm that it is already
running; do not start a stack solely for this exercise:

```bash
docker compose --env-file .env.docker ps
```

One non-destructive Redis exercise is:

```bash
docker compose --env-file .env.docker stop redis
curl -i -X POST http://127.0.0.1:8000/chat/select-mode \
  -H 'Content-Type: application/json' -H 'X-Tab-Id: reliability-smoke' \
  --data '{"mode":"sql"}'
# Expect sanitized 503 session_store_unavailable; no JSON fallback.

docker compose --env-file .env.docker start redis
curl -i http://127.0.0.1:8000/api/ready
# Expect 200 after Redis is healthy and the existing client reconnects.
```

Stopping PostgreSQL instead should make `/api/ready` return sanitized 503; starting it again should
restore readiness after the bounded pool reconnects. Never use `down -v` or remove volumes for a
failure exercise.

## AWS validation status

The Phase 26 ECS task inherits the validated runtime defaults, so no Terraform variables are needed
for Phase 28. Live AWS reliability validation remains pending until the final AWS deployment. This
phase does not add or claim multi-region routing, disaster recovery automation, RDS Multi-AZ by
default, read replicas, cross-region backups, Route 53 failover, distributed circuit state, or an
HA cache topology. Those choices materially affect cost and architecture and require a separate
production decision.

## Deferred

Phase 28 deliberately defers distributed breaker state, generalized HTTP/service retries, bulkheads,
concurrency queues, adaptive retry algorithms, broad chaos infrastructure, and automatic SQL replay.
Performance/load tuning and autoscaling remain Phase 29. AWS HA, multi-region, and disaster-recovery
validation remain deferred as described above.
