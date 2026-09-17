# ADR-027: Provider-neutral observability

- Status: Accepted
- Date: 2026-09-17

## Context

The application needs operational traffic, error, latency, saturation, and correlation signals in
local development and its planned AWS environment. The design must preserve the Phase 23 trust and
privacy boundaries, remain usable without AWS or a collector, avoid high-cardinality cost, and not
turn traces into prompt, SQL, evidence, identity, or reasoning transcripts.

## Decision

Emit structured, centrally redacted JSON logs to stdout in production and readable redacted console
logs in development. Add a bounded `X-Request-Id` middleware backed by context variables; active
trace/span IDs are injected into logs for correlation. Request IDs are not identities or metric
dimensions.

Use OpenTelemetry APIs/SDK and OTLP HTTP for metrics and traces. Instrument only central HTTP,
orchestration, routing, provider-neutral LLM, SQL generation/validation/execution, retrieval,
advanced/multi-hop, forecasting, session, and security boundaries. Attribute and metric dimension
allowlists prohibit content capture and enforce bounded cardinality. SQL instrumentation is manual
and never emits `db.statement`; LLM token metrics use only provider-reported usage.

Use batched, bounded, configurable parent-based trace sampling and periodic metric export.
Telemetry initialization/export/flush failures fail open for business requests, and shutdown flushes
with a bound. The optional local Collector Contrib deployment exports only to debug output. On ECS,
an explicitly versioned conditional ADOT sidecar exports metrics to CloudWatch through EMF and
traces to X-Ray; application/collector logs continue through `awslogs`. IAM is limited to the actual
collector exporters. Retention, sampling, Container Insights, alarms, and notifications use
cost-aware defaults.

## Alternatives considered

- CloudWatch SDK calls throughout business logic: rejected because it couples domain code to AWS.
- Raw prompt/response, retrieved evidence, or SQL logging: rejected as a privacy/security breach.
- SQLAlchemy/Redis automatic instrumentation: rejected because statements, parameters, or keys may
  leak.
- Permanent 100% sampling: rejected for cost and volume; local smoke use is explicitly temporary.
- Request/user/session identifiers as metric dimensions: rejected as high-cardinality and private.
- Datadog/New Relic: rejected because no vendor-specific platform is required.
- A local Grafana/Prometheus/Tempo/Loki stack: rejected as unnecessary Phase 27 operational scope.

## Consequences

The same application telemetry can flow through a local or AWS collector, requests remain functional
without export, and logs/traces can be correlated without content capture. Manual boundary
instrumentation requires deliberate maintenance when central workflows change. Sampling means not
every request has a trace, while logs and metrics remain available. CloudWatch/X-Ray behavior and
cost cannot be claimed until the deferred AWS deployment validates Phase 27B.
