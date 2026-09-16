# Architecture

The Enterprise Conversational Analytics Assistant is being reconstructed as a learning-focused,
clean-room monorepo. It will use synthetic data and generic healthcare analytics examples only.

## Source architecture and reconstruction direction

The source architecture used Azure OpenAI and Databricks SQL. The clean-room reconstruction does
not rewrite that history. Its current direction is AWS-hosted application infrastructure,
PostgreSQL locally and later Amazon RDS PostgreSQL, and provider-neutral AI interfaces. Gemini is
the active development LLM and embedding provider; Azure OpenAI remains an optional adapter.
Amazon Bedrock is a future optional adapter, not a Phase 15 implementation.

Later AWS phases may introduce ECR, ECS/Fargate, RDS PostgreSQL, ElastiCache Redis, S3, Secrets
Manager, CloudWatch with OpenTelemetry, and an Application Load Balancer. None is provisioned in
this phase. Hosting the application on AWS does not require hosting its AI model on AWS: an
AWS-hosted service can call Gemini externally. Identity and RBAC remain a later decision.

## Currently implemented

- Repository foundation for backend, frontend, documentation, and scripts
- FastAPI backend application
- Environment-backed, validated configuration
- YAML-backed, Pydantic-validated functionality flags
- Health endpoint at `GET /api/health`
- Safe feature flag endpoints at `GET /api/ui-feature-flags` and `GET /api/tool-flags`
- Canonical chat-mode contract and welcome endpoint at `GET /api/chat-mode/welcome`
- FastAPI application factory, central router composition, and controlled API error envelope
- Per-tab mode selection and conversation reset endpoints
- Typed JSON session persistence behind a `SessionStore` abstraction
- Provider-neutral LLM and embedding contracts with lazy Gemini and Azure OpenAI adapters
- Deterministic privacy preprocessing with request-scoped identifier tokenization
- Typed supervisor routing with deterministic heuristics and structured LLM classification
- Five-node LangGraph for metadata-grounded, unexecuted PostgreSQL generation
- PostgreSQL-oriented SQLAlchemy models for seven synthetic healthcare tables
- Alembic migration infrastructure and one initial schema migration
- Deterministic, reset-safe synthetic data seeding
- Database-independent `QueryExecutor` contract with a PostgreSQL implementation
- SQL AST validation and read-only, timed, bounded query execution
- Typed physical and semantic metadata models
- PostgreSQL schema introspection merged with version-controlled YAML business semantics
- Deterministic metadata context generation and schema-drift validation
- Accepted-SQL execution with privacy-safe summaries and deterministic chart metadata
- Hierarchical-first Knowledge Catalog retrieval with LanceDB hybrid fallback
- Deterministic Data Discovery, grounded Data Quality guidance, and two-hop Semantica retrieval
- Internal aggregate forecasting with deterministic backtesting, selection, and intervals
- Thin application-level chat orchestration over the existing specialists
- React/TypeScript/webpack One UI with typed specialist result rendering
- Automated backend test foundation

## Feature flags

Feature flags centralize rollout configuration in
`backend/config/functionality_flags.yaml`. The configuration is divided into UI, tool, retrieval,
reasoning, and observability groups. Pydantic validates the file once, and the application caches
the validated immutable models for the process lifetime.

Currently implemented behavior is limited to YAML loading, configuration validation, caching, and
the UI/tool API projections. The endpoint models deliberately exclude reasoning thresholds,
retrieval settings, and observability settings.

Knowledge Catalog and the three Phase 15 retrieval specialists are implemented. Tool flags remain
UI rollout controls and are not automatically enabled by backend readiness. Phase 16 implements
gated generic advanced reasoning and SQL-specific multi-hop analysis; both reasoning flags remain
off by default. Phase 17 implements the internal forecasting tool while its tool flag remains off
by default. Phase 18 consumes the frontend-safe projections to control presentation while keeping
all security and routing decisions on the backend. Observability providers remain unimplemented.

## Analytical database

The source architecture uses Databricks SQL. The clean-room reconstruction uses PostgreSQL as a
local development substitute; this is an intentional reconstruction decision, not a claim about
the original production database. SQLAlchemy 2.x defines the typed relational model, Psycopg 3 is
the synchronous driver, and Alembic is the only development schema-management workflow.

The Phase 3 schema contains members, facilities, providers, encounters, claims, claim lines, and
appointments. It supports future analytical joins while enforcing foreign keys, controlled domain
values, and exact monetary constraints.

Phase 4 provides an internal `QueryExecutor` seam for future PostgreSQL and Databricks
implementations. The PostgreSQL executor requires separate query credentials and combines sqlglot
AST inspection with database-role permissions, read-only transactions, statement timeouts, bounded
fetching, and sanitized errors. It does not expose arbitrary SQL over HTTP and does not perform
future NLP-to-SQL semantic validation.

## Metadata foundation

Phase 5 establishes this internal flow:

```text
PostgreSQL
    ↓
Metadata Introspection
    +
Semantic Catalog
    ↓
Metadata Registry
```

PostgreSQL supplies physical schema facts and the YAML catalog supplies business descriptions,
aliases, value hints, table grain, and analytical notes. Registry construction detects drift, and a
development refresh command writes an ignored JSON snapshot for inspection. Phase 11 reuses this
registry for domain selection, candidate-table derivation, selected-table context, and grounded SQL
generation; it does not create a second metadata source.

## API application layer

Phase 6 keeps application assembly in `create_app()` and composes the implemented route modules in
one API router. The chat-mode welcome request follows this flow:

```text
HTTP
  -> FastAPI route
  -> ChatModeService
  -> immutable ChatModeRegistry
  -> typed response
```

The seven canonical top-level modes are product contracts backed by static configuration. They
remain independent of tool feature flags. Unknown modes return a controlled HTTP 400 response
rather than silently falling back to `auto`. Phase 18 adds the conversational `POST /chat`
pipeline and specialist execution. Forecasting remains an internal SQL strategy rather than a
top-level mode.

## Phase 18 One UI and chat orchestration

```text
React One UI
    |
POST /chat
    |
ChatOrchestrator
    |
PrivacyProcessor
    |
Session selected mode
    |
Supervisor
    |
ReasoningPromotionPolicy (where applicable)
    |
SpecialistRegistry
    |-- Standard NLP2SQL
    |-- MultiHop NLP2SQL
    |-- Forecasting
    |-- Knowledge Catalog
    |-- Data Discovery
    |-- Data Quality
    `-- Semantica
```

The orchestrator owns current-turn sequencing, not specialist logic. It accepts only a message,
bounded current-turn context, and a typed Data Intelligence strategy. The selected top-level mode
comes from the server session. Raw user-facing history is persisted; safe working text, custom
context, and mapping history are not. Only the latest token mapping required by the accepted SQL
execution contract is retained.

Standard SQL deliberately crosses two requests:

```text
POST /chat
    -> accepted final_sql
    -> session.last_generated_sql
    -> React Run Query
    -> POST /chat/execute-sql (no client SQL)
    -> QueryExecutor
    -> rows + summary + chart
    -> React
```

The React client uses `HashRouter`, native `fetch`, the server-managed cookie, and a stable
sessionStorage `X-Tab-Id`. It renders response discriminators rather than reproducing routing or
analytics logic. Advanced results expose only their synthesized output, and the browser never
receives resolved sensitive SQL or privacy mappings. See
[`ADR-018`](decisions/ADR-018-one-ui-chat-orchestration.md).

## Session state

Phase 7 identifies a logical conversation with an opaque browser-session cookie plus a validated
`X-Tab-Id` header. The composite identity is converted to a deterministic SHA-256 storage key, and
typed state is persisted through this boundary:

```text
HTTP request
  -> browser cookie + X-Tab-Id
  -> SessionService
  -> SessionStore
  -> atomic local JSON artifact
```

Tabs sharing a browser cookie remain isolated. Reset clears only the current tab's conversational
fields and preserves its selected mode. Privacy mappings are request-scoped and
`token_mapping_history` is not part of `SessionState`; `custom_context` will be sent fresh with
future chat turns. Neither appears in persisted session JSON. `last_token_mapping` remains the
only optional durable slot for a future chat service to assign for the latest turn. Local file
storage uses process-local locking and is not a horizontally scalable production state solution.

## LLM provider boundary

Phase 8 introduced the provider-neutral `LLMClient`; Phase 15 adds provider selection:

```text
Application workflow
  -> typed LLMRequest
  -> LLMClient
       -> GeminiLLMClient (development default)
       -> AzureOpenAILLMClient (optional)
  -> typed text or Pydantic result
```

SDK clients are created only when selected functionality runs, so FastAPI startup remains
independent of Gemini and Azure credentials. System/user roles, structured output, usage mapping,
SDK retry policy, and safe errors remain adapter concerns. `EmbeddingClient` applies the same
boundary to LanceDB indexing. Index manifests prevent cross-provider/model/dimension vector reuse.
Future Bedrock adapters can implement these contracts without changing agents.

## Phase 15 specialists

```text
data_discovery -> MetadataRegistry -> deterministic ranked dataset matches
data_quality   -> synthetic DQ evidence -> LLMClient -> validated citations
semantica      -> LanceDB hybrid seeds -> adjacency (0..2 hops) -> LLMClient -> citations
```

Data Discovery is for specific dataset/table/schema lookup and uses no model, embedding, or row
query. Data Quality provides documented guidance only and performs no live profiling. Semantica
uses its own 900/120 chunks, `semantica_chunks` table, and deterministic graph artifact. All three
specialist endpoints apply privacy processing at the API boundary. The supervisor continues to
route only; it does not execute specialists, and full `POST /chat` remains unimplemented.

## Phase 16 advanced reasoning

Generic tool coordination and SQL-specific multi-hop analysis remain separate:

```text
PrivacyProcessor -> Supervisor -> SupervisorDecision -> ReasoningPromotionPolicy
                                                        | STANDARD -> specialist
                                                        ` ADVANCED
                                                             |
                                      decompose -> plan_tools -> execute
                                                             |
                                      synthesize <- reflect <-+

safe question -> MultiHopNLP2SQLAgent -> plan hops
  -> validated standard NLP2SQL + bounded read-only execution per hop
  -> protected intermediate previews -> structured final synthesis
  -> summary + table + grounded deltas
```

Promotion is deterministic and requires the existing flag, confidence threshold, eligible route,
enabled agent, and available approved tool. The generic planner has no unrestricted execution
tools and permits at most one replan. Multi-hop validates an acyclic dependency plan, reuses the
standard Phase 11–13 pipeline for every query, and enforces hop, per-hop row, total row, and
monotonic time limits in application code. Only bounded privacy-protected result previews reach
later model calls. Both workflows depend only on `LLMClient`; standard tests use fakes.

The flags remain disabled by default, no public reasoning endpoint or full chat orchestration is
added, and Phase 16 requires no AWS resources or credentials. See
[`advanced-reasoning.md`](advanced-reasoning.md) and
[`multihop-nlp2sql.md`](multihop-nlp2sql.md).

## Phase 17 forecasting

Forecasting is a dedicated internal specialist beneath Data Intelligence:

```text
safe question -> typed LLM plan -> standard NLP2SQL ACCEPT/final_sql
  -> token resolution -> existing bounded PostgreSQL QueryExecutor
  -> deterministic regular-series validation and holdout model selection
  -> all-history refit -> forecast + approximate intervals
  -> protected-preview LLM explanation with deterministic fallback
```

Only aggregate day/week/month operational measures are supported. Individual clinical-outcome
prediction is rejected. Forecast values come only from dependency-free Python models; the LLM may
plan and explain but cannot calculate or alter them. The agent reuses Phase 11–13 boundaries, has
no public endpoint, and can enter the Phase 16 advanced registry only when the existing route and
tool flags are enabled. See [`forecasting.md`](forecasting.md) and
[`ADR-017`](decisions/ADR-017-deterministic-forecasting.md).

## Privacy boundary

Phase 9 adds deterministic internal privacy preprocessing ahead of LLM-backed routing:

```text
Raw user text
  -> PrivacyProcessor
  -> safe_text
  -> SupervisorMultiAgent

LLM or future specialist response
  -> ResponseUnmasker
  -> user-facing response
```

The processor replaces exact Phase 3 synthetic business identifiers with reversible,
request-scoped `Txxx` tokens and irreversibly replaces supported email addresses and US phone
formats with category placeholders. Response unmasking restores only standalone tokens present in
the current request mapping. The privacy package does not access routes, sessions, PostgreSQL,
query execution, or an LLM, and it does not log prompts or mappings. It is a narrow deterministic
baseline rather than comprehensive clinical free-text de-identification. Specialist execution and
complete `POST /chat` orchestration remain future work.

## Supervisor and intent routing

Phase 10 stops at a typed routing decision:

```text
Raw user text
  -> PrivacyProcessor
  -> safe_text
  -> SupervisorMultiAgent
       -> explicit non-auto mode policy ------------------+
       -> narrow deterministic heuristic ----------------+-> SupervisorDecision
       -> IntentRouterAgent -> structured LLM decision ---+
  -> future specialist (not implemented)
```

An explicit non-`auto` top-level mode is a hard constraint and bypasses the general LLM classifier.
SQL mode may use a narrow forecast heuristic to select the internal `forecasting` sub-route. Auto
mode evaluates high-confidence access, data-quality, explicit Semantica, help, greeting, forecast,
and specific data-discovery rules before requesting a structured LLM decision. Classifier results
below `INTENT_ROUTER_MIN_CONFIDENCE` fall back to `knowledge_catalog`. Provider failure is reported
as an error rather than disguised as classification uncertainty.

`config/agents_registry.yaml` controls internal route eligibility independently from UI/tool
feature flags. A registered route is eligible for selection; it does not imply that its specialist
exists. Disabled explicit modes fail without substitution. Disabled auto-mode results use the
enabled knowledge-catalog fallback or fail when that fallback is unavailable. The supervisor does
not access metadata, execute SQL, retrieve content, invoke specialists, or expose an HTTP endpoint.

Future chat orchestration will hand a `route=sql` decision to the Phase 11 generation pipeline.

## Standard NLP-to-SQL generation

Phase 11 implements only the standard SQL generation stages:

```text
route=sql
  -> NLP2SQLAgent
  -> LangGraph StateGraph
       -> refresh_metadata
       -> select_domains
       -> select_tables
       -> build_metadata
       -> generate_sql
  -> generated PostgreSQL SQL (untrusted and unexecuted)
  -> Phase 12 validator (future)
  -> Phase 13 execution and presentation (future)
```

The graph state is a `TypedDict` containing only the privacy-safe question and workflow-derived
domain, table, metadata, SQL, and call-count values. It never contains the raw question, token
mappings, credentials, or session state. Pydantic models constrain all three LLM outputs, while
the graph uses the provider-neutral `LLMClient` rather than an Azure adapter.

Domain selection sees compact domain names, descriptions, and aliases. Candidate tables are then
derived from `MetadataRegistry.tables_for_domain()`, and table selection sees only those table
summaries, their grain, aliases, and direct candidate relationships. The existing deterministic
metadata context builder supplies full selected-table columns, types, key relationships, semantic
hints, and analytical notes to the final PostgreSQL generation call.

The documented source system generates Databricks SQL. PostgreSQL is the deliberate local
clean-room target in this phase. Generated SQL is not syntax-checked, scored, rewritten, passed to
the Phase 4 guard, or executed. Prompt constraints are guidance only; Phase 12 will add the actual
validation boundary before Phase 13 can execute anything.

## Planned

The following capabilities are architectural direction, not current implementation:

- Phase 19 AI Dashboard
- Authentication, production infrastructure, deployment, and observability

Components will be introduced incrementally. Each phase should preserve clear boundaries between
HTTP transport, application logic, integrations, and data access without creating unused
abstractions in advance.
