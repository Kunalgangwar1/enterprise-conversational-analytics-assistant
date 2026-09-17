# Observability

Phase 27A adds provider-neutral operational visibility without making telemetry part of application
correctness. Phase 27B—observing real CloudWatch and X-Ray data—remains deferred until the AWS
environment is deployed.

## Architecture

```text
FastAPI -> JSON stdout logs --------------------------> ECS awslogs -> CloudWatch Logs
        -> OpenTelemetry metrics/traces -> OTLP/HTTP -+-> local contrib collector -> debug output
                                                      `-> ECS ADOT sidecar
                                                           |-> CloudWatch metrics (EMF)
                                                           `-> X-Ray traces
```

Logs describe discrete events, metrics aggregate bounded operational signals, and traces connect a
sampled request to central operations. Application code never calls a proprietary CloudWatch or
X-Ray API. `OBSERVABILITY_ENABLED=false` is the safe local/test default; no collector, AWS
credentials, or internet connection is then required. Export initialization, flush, and shutdown
fail open and do not fail a request.

## Configuration

The safe settings are documented in `.env.example`. Important controls are `LOG_FORMAT`,
`OBSERVABILITY_ENABLED`, `SERVICE_NAME`, `SERVICE_VERSION`, `OTEL_EXPORTER_OTLP_ENDPOINT`,
`OTEL_TRACE_SAMPLE_RATIO`, `OTEL_EXPORT_TIMEOUT_SECONDS`, `METRICS_ENABLED`, and
`TRACING_ENABLED`. Only `http/protobuf` is accepted. The endpoint validator rejects credentials,
queries, and fragments. Production uses JSON logs. The default trace ratio is 0.10; the local
overlay deliberately uses 1.0 so a developer can see a short smoke request. A deployed production
ratio must be tuned from traffic and cost evidence rather than left at 100%.

Traces use a parent-based ratio sampler, a bounded 512-span queue, batches of at most 128, a
two-second scheduled delay, and bounded exporter timeouts. Metrics export periodically every 30
seconds. Providers are flushed during FastAPI shutdown before being closed.

## Structured logs and correlation

JSON records always contain `timestamp`, `level`, `logger`, `message`, `service`,
`service_version`, and `environment`. Safe optional fields are `request_id`, `trace_id`, `span_id`,
`route`, `operation`, `outcome`, safe error code/type, provider, and model. Null fields are omitted.
Console logging uses the same redactor.

The request middleware accepts `X-Request-Id` only when it is 1–64 ASCII alphanumeric/`._-`
characters and starts alphanumerically; otherwise it creates an opaque UUID. The response returns
the resolved ID. It is correlation metadata, never identity or authorization input. Context
variables make request and active span identifiers available to deep logs without changing every
function signature. Standard incoming `traceparent`/`tracestate` is extracted, but request bodies,
query strings, cookies, and authorization headers are not captured.

Troubleshooting flow:

1. Copy `X-Request-Id` from the failed response.
2. Search application logs for `request_id` and note `trace_id` when present.
3. Search X-Ray by that trace ID and inspect only the bounded operational span attributes.
4. Compare the time window with the dashboard and alarms. A missing trace can be normal sampling;
   the request log remains authoritative.

## Privacy and redaction

The centralized formatter redacts Bearer values, JWT-shaped strings, PostgreSQL/Redis DSNs, and
credential-like assignments. It also allowlists extra structured fields. The telemetry policy
prohibits authorization/cookie values, API/provider keys, database or Redis credentials, raw
prompts, `custom_context`, token mappings, SQL text/parameters, retrieved bodies/chunks, LLM
request/response bodies, principal email/groups/subject, session IDs/keys, member/claim IDs, and
hidden planner reasoning. Exception messages are not attached to spans. This is defense in depth;
callers should still avoid constructing sensitive log messages.

## Cardinality policy

Metric dimensions must be listed in the catalog below and pass the central sanitizer. Routes,
selection sources, outcomes, reason codes, retriever types, providers, forecast models, methods,
and status classes use fixed sets. HTTP route values are framework templates, never raw paths.
Configured model labels are syntax/length bounded. The following are forbidden dimensions:
`request_id`, `trace_id`, session/user/email/member/claim identifiers, IP addresses, raw paths,
prompts, SQL or SQL hashes, error messages, and document/chunk IDs. Safe correlation IDs may appear
in logs/traces, but never metrics.

## Metric catalog

All durations use seconds. No arbitrary dimensions are accepted.

| Metric | Type | Unit | Meaning | Allowed dimensions |
|---|---|---:|---|---|
| `http.server.requests` | counter | request | Completed requests | method, route, status_class |
| `http.server.errors` | counter | request | HTTP responses at 4xx/5xx | method, route, status_class |
| `http.server.duration` | histogram | s | Request latency | method, route, status_class |
| `http.server.active_requests` | up/down counter | request | Requests in flight | method |
| `routing.requests` | counter | request | Supervisor decisions | route, selection_source |
| `routing.fallbacks` | counter | request | Fallback decisions | route |
| `llm.requests` | counter | request | Provider-neutral calls | provider, model, operation, outcome |
| `llm.errors` | counter | request | Failed LLM calls | provider, model, operation, outcome |
| `llm.duration` | histogram | s | LLM call latency | provider, model, operation, outcome |
| `llm.tokens.input` | counter | token | Provider-reported input usage | provider, model, operation |
| `llm.tokens.output` | counter | token | Provider-reported output usage | provider, model, operation |
| `sql.generation.duration` | histogram | s | SQL generation latency | outcome |
| `sql.validation.decision` | counter | decision | Accept/reject/rewrite decisions | validation_decision |
| `sql.validation.rewrites` | counter | rewrite | Validator rewrites | outcome |
| `sql.execution.duration` | histogram | s | Read-only query latency | outcome |
| `sql.execution.rows` | histogram | row | Returned row count | outcome |
| `sql.execution.truncated` | counter | query | Results capped by row bound | outcome |
| `sql.execution.errors` | counter | query | Query failures/timeouts | outcome |
| `retrieval.requests` | counter | request | Retrieval operations | retriever_type, outcome |
| `retrieval.duration` | histogram | s | Retrieval latency | retriever_type, outcome |
| `retrieval.result_count` | histogram | result | Evidence count | retriever_type |
| `retrieval.no_evidence` | counter | request | Empty retrievals | retriever_type |
| `advanced_reasoning.requests` | counter | request | Advanced planner runs | outcome |
| `advanced_reasoning.tool_calls` | counter | call | Policy-approved tool calls | outcome |
| `advanced_reasoning.replans` | counter | replan | Bounded replans | outcome |
| `advanced_reasoning.budget_violations` | counter | violation | Policy budget rejections | outcome |
| `multihop.requests` | counter | request | Multi-hop SQL runs | outcome |
| `multihop.hops` | histogram | hop | Hops in a completed run | outcome |
| `multihop.failures` | counter | request | Failed multi-hop runs | outcome |
| `forecast.requests` | counter | request | Forecast operations | outcome |
| `forecast.duration` | histogram | s | Forecast latency | outcome |
| `forecast.model_selected` | counter | selection | Deterministic model selection | model_selected |
| `forecast.errors` | counter | request | Forecast failures | outcome |
| `session.conflicts` | counter | conflict | Optimistic update conflicts | operation |
| `session.unavailable` | counter | failure | Store unavailable events | operation |
| `session.operation.duration` | histogram | s | Load/update latency | operation, outcome |
| `auth.authentication_failures` | counter | failure | Missing/invalid authentication | reason_code, route_category |
| `auth.authorization_denials` | counter | denial | Permission denials | reason_code, route_category |
| `security.rate_limited_requests` | counter | request | Limit/storage rejections | reason_code, route_category |
| `security.request_too_large` | counter | request | Oversized request rejection | reason_code, route_category |

Token counters are emitted only from reliable provider response usage; the application does not
estimate them.

## Span catalog

Manual spans exist only at central boundaries: `http.request`, `chat.orchestrate`, `routing.select`,
`specialist.execute`, `llm.call`, `sql.generate`, `sql.validate`, `db.query`, `retrieval.search`,
`forecast.run`, `session.load`, and `session.update`. Attributes are centrally allowlisted and limited to
method/route/status, operation/outcome, provider/model, selected mode/route/strategy/result type,
authorization outcome, PostgreSQL operation/row count/truncation/timeout, retriever type/result
count, forecast model, and session operation. There is no `db.statement`, prompt/content capture,
retrieval content, Redis key, chain-of-thought, or raw exception message.

## Local collector

The base Compose stack is unchanged. Start the optional upstream Collector Contrib overlay with:

```bash
docker compose -f compose.yaml -f compose.observability.yaml up --build
```

`observability/otel-collector-local.yaml` accepts OTLP HTTP on 4318 and sends traces/metrics only to
the debug exporter. It contains a memory limiter and batch processor and never sends local data to
AWS. No Prometheus, Grafana, Tempo, Loki, or Elasticsearch service is introduced.

## AWS design

When `observability_enabled=true`, the ECS task adds the explicitly pinned
`public.ecr.aws/aws-observability/aws-otel-collector:v0.49.0` ADOT sidecar. Its non-secret config is
stored in SSM Parameter Store and receives OTLP HTTP from the colocated backend. Traces use the
`awsxray` exporter. Metrics use `awsemf` with the deterministic
`EnterpriseConversationalAnalytics` namespace and a dedicated bounded-retention log group. Backend
and collector stdout use separate `awslogs` log groups. The task role grants only X-Ray write plus
the required application-metric log stream actions; it does not attach AWS managed full-access
policies.

The Terraform dashboard covers ALB traffic/latency/4xx/5xx, ECS CPU/memory, RDS CPU/connections/free
storage, cache CPU/memory/connections, and defined application HTTP metrics. Eight optional alarms
cover unhealthy targets, backend 5xx count, ECS CPU/memory, RDS CPU/free storage, and cache
CPU/memory. Thresholds are initial operational objectives—not measured SLO guarantees. An optional
SNS topic is created without subscriptions. Container Insights is configurable and disabled in the
cost-aware development example; the production example enables it.

## Cost and troubleshooting

Primary cost drivers are CloudWatch log ingestion/storage, custom metrics, Container Insights,
X-Ray storage/analysis, trace sampling, and retention. Keep dev observability/alarms/Container
Insights off until needed, keep retention bounded, avoid high-cardinality data, and use conservative
sampling.

- No local telemetry: check `OBSERVABILITY_ENABLED`, the backend endpoint
  `http://otel-collector:4318`, and collector debug logs.
- Export errors: confirm collector reachability; the request should still succeed.
- No AWS traces/metrics: verify the sidecar is running, inspect its separate log group, confirm the
  SSM config reference and narrow task-role permissions, and check the sampling ratio.
- Missing request correlation: use the returned request ID; unsampled traces intentionally have no
  trace ID.
- Dashboard has no custom metrics: confirm observability is enabled and wait beyond the periodic
  export interval. Do not infer successful export until Phase 27B live validation.

CloudWatch Application Signals is not required. It may be evaluated later as an optional extension
after real workload and cost data exist.
