# Performance and scalability

Phase 29 adds bounded, reproducible local/CI performance tooling. It does not assert production
capacity and does not contact Gemini, Azure OpenAI, or AWS.

## Measure-first findings

The initial production frontend build took 12.26 seconds on the Phase 29 workstation, peaked at
820,620 KiB RSS, and emitted a 717,515-byte main JavaScript asset. Recharts was reachable from the
initial chat bundle through SQL and forecasting result components. Those visualizations are now
loaded only when their result type is rendered, and webpack emits stable runtime/vendor chunks. The
post-change build took 11.69 seconds and reduced the initial entrypoint to 340 KiB (runtime 3.65
KiB, shared vendor 307 KiB, application 29.6 KiB). The deferred Recharts chunk is 372 KiB. These
machine-local figures are comparison evidence, not performance guarantees.

Database pools already had pre-ping, finite acquisition/connect timeouts, size, and overflow bounds.
Phase 29 adds configurable connection recycling. Retrieval agents are initialized lazily once per
application process; no per-request index rebuild was found, so retrieval code was not changed.
The backend image was already multi-stage, excludes development/test artifacts, and installs the
locked production dependency set only. A measured build was 1,080,785,801 bytes, with a 677 MB
virtual-environment layer. The builder had also precompiled 6,487 dependency files while the runtime
explicitly disables bytecode writes. Phase 29 therefore removes that duplicate precompilation; the
optimized image is 946,603,051 bytes (134,182,750 bytes, or 12.4%, smaller) and its environment
layer is 571 MB. The remaining large scientific/vector dependencies are retained because they are
application features.

## Workloads and profiles

`backend/performance/locustfile.py` uses stable request names and synthetic inputs. It covers
liveness, Data Discovery, dashboard SQL, session selection, chat, and execution of server-owned
validated SQL. Start the target with `performance.fake_app`; that target invokes a network-free
FakeLLM for chat while retaining real PostgreSQL and Redis paths for dashboard, SQL, sessions, and
rate limiting.

| Profile | Users | Spawn/s | Duration | Intended use |
|---|---:|---:|---:|---|
| smoke | 2 | 1 | 15s | CI/manual harness verification |
| baseline | 10 | 2 | 1m | modest reviewed local comparison |
| stress | 50 | 5 | 5m | manual-only saturation exploration |

From `backend/`, after starting PostgreSQL/Redis, migrating, and seeding synthetic data:

```bash
uv run uvicorn performance.fake_app:app --host 127.0.0.1 --port 8000
uv run python -m performance.run --profile baseline
# Run the printed command, then:
uv run python -m performance.report --profile baseline \
  --stats ../artifacts/performance/runs/latest/locust_stats.csv \
  --output ../artifacts/performance/runs/latest
```

The harness refuses `PERFORMANCE_ALLOW_LIVE_LLM=true`. Do not point it at a live-provider process.
Run artifacts contain p50/p90/p95/p99, average/max latency, throughput, count, failure count/rate,
profile, Python/platform metadata, and threshold results in JSON and Markdown. Raw runs are ignored;
only a reviewed baseline is promoted under `artifacts/performance/baselines/`.

Default local gates are failure rate <=1%; health p95/p99 <=250/500 ms; Data Discovery and session
p95/p99 <=750/1500 ms; and SQL/dashboard/FakeLLM chat p95/p99 <=1500/3000 ms. They are initial
engineering regression alarms, not production SLOs. Global defaults are command-configurable and
the lightweight-route overrides are explicit in `performance/thresholds.py`.

The metric definitions follow Locust: RPS is completed requests per second; failure rate is failed
requests divided by requests; p50/p90/p95/p99 are observed response-time percentiles; average and
maximum are supporting diagnostics rather than the primary gate.

## Local development baseline

No HTTP latency baseline was run. Docker Compose was not active (only an unrelated MySQL container
was running), and starting/rebuilding the full dependency stack solely for numbers was not justified.
The intended dataset is the current deterministic seed: 12 facilities, 80 providers, 500 members,
3,000 encounters, 2,500 claims, and 1,500 appointments. This is demo scale, not enterprise scale.

| Area | Before | Change | After | Impact | Tradeoff |
|---|---:|---|---:|---|---|
| Frontend initial entrypoint | 701 KiB | lazy charts + split chunks | 340 KiB | 51.5% smaller initial entrypoint | charts load on first use |
| Backend image | 1,080,785,801 B | omit redundant bytecode compilation | 946,603,051 B | 12.4% smaller | first imports are not precompiled |
| HTTP workload | not measured | harness added | not measured | repeatable future evidence | requires PostgreSQL/Redis stack |

## Database connection budget

The conservative upper bound is:

```text
tasks × workers/task × pools/worker × (pool_size + max_overflow) + reserve
```

The current AWS defaults are 3 maximum tasks, 1 worker, 3 possible engines, `(5 + 5)` connections,
plus 10 reserved connections: 100 total. Terraform rejects a shape above the explicit budget.
The multiplier is deliberately conservative because application readiness, dashboard, and SQL
execution can own separate engines. Recalculate against the selected RDS class before every plan.
Do not increase workers or task maximum independently of this calculation.

`pool_pre_ping`, five-second acquisition/connect timeouts, a 30-minute recycle age, bounded size and
overflow, statement timeouts, row caps, SELECT-only credentials, and SQL validation remain intact.

## Horizontal scaling and state

Backend instances are stateless only when production uses shared Redis sessions and rate limiting.
Browser/tab identity remains in the signed cookie/header contract; conversation state is in Redis.
No in-memory production fallback exists. PostgreSQL is shared, and generated artifacts are not a
cross-replica coordination mechanism. Health is liveness-only; readiness checks required shared
dependencies. Scale-in uses graceful ECS task shutdown and the application closes providers,
pools, Redis, and telemetry.

Optional ECS target tracking is disabled by default. When enabled it uses both average CPU and
memory targets, bounded min/max capacity, a 60-second scale-out cooldown, and conservative
300-second scale-in cooldown. These defaults still require live validation for warm-up time,
draining, sticky state assumptions, Redis pressure, database pressure, and alert tuning.

## Bottlenecks and boundaries

Expected local bottlenecks are PostgreSQL aggregate queries, separate per-process pools, Redis
round trips for session/rate-limit state, and visualization bundle parsing on first use. LLM latency
is intentionally excluded from load runs. Retrieval setup is process-local and lazy; vector search
quality and topology were not changed. The harness can reveal regressions but cannot predict AWS
capacity, concurrency ceilings, RDS/Valkey sizing, provider quotas, or regional network latency.

LanceDB indexes are packaged/local immutable assets per application task. Agent construction is lazy
and process-local; replicas therefore duplicate index storage and handles, and an updated index
requires an immutable image/asset rollout so replicas remain consistent. This is acceptable at the
current scale. Future measured options may include shared immutable object distribution or a managed
vector service, but Phase 29 does not change backend, chunking, ranking, graph distance, or embeddings.

No database index or query was changed because no slow deterministic query was measured. No
user-result, chat, SQL-result, session, JWT, or provider-response cache was added. Process-local
circuit breakers and immutable configuration/index handles are non-authoritative and acceptable per
replica. One-shot bootstrap, migrations, and optional seed remain separate from replica startup.

CloudFront already fronts static delivery and can negotiate compression; local nginx serves the
frontend. API compression was not duplicated in FastAPI without payload evidence. Response contracts
and Pydantic serialization remain unchanged.

## CI, recovery, and interpretation

The weekly/manual performance workflow creates PostgreSQL and Redis services, migrates and seeds
synthetic data, runs the FakeLLM target, executes only the smoke profile, gates thresholds, and
uploads artifacts for 14 days. It is separate from pull-request CI to avoid noise and cost.

A failing latency gate means the measured workflow exceeded a local comparison threshold; inspect
per-request percentiles and failure CSV before changing code. A failure-rate gate is always
actionable. Confirm dataset, runner, dependency versions, and commit before comparing runs. Never
publish machine-specific throughput as a production capacity claim.

## Deferred live work

AWS load tests, real LLM/provider latency, RDS/Valkey capacity, ECS autoscaling response, multi-task
session continuity, cost/concurrency limits, and production-grade SLO tuning remain deferred until
deployment. Multi-region, disaster recovery, read replicas, and high-availability topology are not
implemented by Phase 29.

After AWS deployment, an operator may manually point the same bounded scenarios at the CloudFront
URL, start with smoke, then increase concurrency in reviewed steps. At each step observe CloudFront
and ALB latency/errors, ECS CPU/memory, application p95/p99, RDS CPU/connections/free resources,
Valkey CPU/memory/connections, bounded application metrics, X-Ray traces, and scaling events. Stop at
errors, budget limits, or dependency pressure. Never schedule an AWS stress run after deployment.
Initial engineering objectives remain the local gates above; every AWS capacity, latency, warm-up,
draining, RDS, Valkey, vector, provider, cost, and concurrency objective is pending AWS validation.
