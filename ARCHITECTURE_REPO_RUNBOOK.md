# PDAP Chatbot Architecture Runbook

## Objective
This repository provides a multi-mode enterprise chatbot with one backend and one React UI, plus an AI Dashboard authoring tool built on the same NLP2SQL foundation.

Supported chat modes (`CHATBOT_MODE_CONFIG` in `backend/server_core/config/chat_modes.py`):
- auto ("PDAP AI"): supervisor mode that routes to the right specialist automatically
- sql ("Data Intelligence"): NLP-to-SQL generation and execution, with Standard, Advanced Reasoning (multi-hop), and Healthcare Forecasting sub-modes
- group_access ("Data Access Assistant"): access and entitlement request support
- data_discovery ("Data Discovery"): dataset-first retrieval filtered to repos that start with datasets-
- knowledge_catalog ("PDAP Ontology"): hierarchical index-traversal retrieval over the knowledge catalog, combined with FAISS/LanceDB hybrid vector search when hierarchical results are insufficient
- semantica ("Semantica"): graph-enriched retrieval over indexed workspace/source content
- data_quality ("Data Quality"): completeness/freshness/validity assessment and remediation guidance

The legacy "graph_knowledge_catalog" Graph RAG mode has been folded into `knowledge_catalog`'s hybrid pipeline; old links/aliases (`graph_knowledge_catalog`, `graph_catalog`, `rag`, `unified_planner`) still resolve via `CHATBOT_ROUTE_ALIASES`/`LEGACY_CHATBOT_MODE_ALIASES` for backward compatibility.

A separate tool, **AI Dashboard** (`/dashboard`), generates multi-widget analytics dashboards (KPIs + charts) from a chat prompt or a reference image, reusing the NLP2SQL pipeline per widget. It is not part of the chat intent-routing flow above — its frontend calls a dedicated `/api/dashboards/*` REST surface directly.

## Runtime Stack
- Backend: FastAPI app served by Uvicorn on port 8000 (`backend/server_core/chat_server.py`, `create_app()`/`main()`). A Flask-compatible `Blueprint`/route-decorator shim (`server_core/infra/http_compat.py`) is used so route handlers still read like Flask views; do not assume Flask conventions (e.g. WSGI, `app.run()`) apply.
- Frontend: React + TypeScript app on port 5173 (webpack dev server, HashRouter — routes are addressed as `/#/...`)
- LLM: Azure OpenAI (`backend/utils/azure_openai_client.py`), optional Anthropic gateway
- SQL engine: Databricks SQL (connection pool in `backend/utils/databricks_tools.py`)
- Retrieval: LanceDB vector stores (conceptually FAISS-like; older docs/notes say "FAISS") plus hierarchical Markdown catalog traversal and Semantica graph expansion
- Knowledge catalog source: the Markdown tree configured by `KNOWLEDGE_CATALOG_DIR`
- Observability: structured `chatbot.*` logs, OpenTelemetry (OTLP), Langfuse, MLflow (Databricks tracking), AgentOps — all toggled in `backend/FUNCTIONALITY_FLAGS.yaml`, soft-fail if unconfigured

### Clean-room reconstruction direction

The runtime stack above describes the source architecture: Azure OpenAI and Databricks SQL. The
learning reconstruction intentionally targets PostgreSQL locally and Amazon RDS PostgreSQL later,
with AWS as the future application platform. Gemini is the active development LLM and embedding
provider behind `LLMClient` and `EmbeddingClient`; the Azure OpenAI adapters are retained as
optional providers. Amazon Bedrock is a future optional adapter and is not implemented in Phase 15.

Later AWS phases may use ECR, ECS/Fargate, RDS PostgreSQL, ElastiCache Redis, S3, Secrets Manager,
CloudWatch with OpenTelemetry, and an Application Load Balancer. No AWS resources are created in
this phase. An AWS-hosted application can call Gemini externally; AWS hosting does not require an
AWS-hosted model.

## Request Flow
1. User sends a message from One UI.
2. Backend route receives the turn in `server_core/api/routes.py`.
3. `chat_flow_service.py` redacts and token-maps identifiers (`PHIPIIRedactionAgent`, `agents/mapping_funs.py`).
4. `SupervisorMultiAgent` (`server_core/supervisor_multi_agent.py`) routes by intent via `IntentRouterAgent`.
5. Simple/high-confidence single-intent requests may be promoted to `AdvancedReasoningPlanner` (a LangGraph decompose→plan_tools→execute→reflect→synthesize loop) when `DEEP_AGENT_SINGLE_INTENT_ENABLED` is on and confidence/eligible-route conditions are met; otherwise the matched specialist handler runs directly.
6. Route handler executes mode-specific logic.
7. Response is unmasked, shaped (Markdown/response-presentation), and returned to UI.
8. UI renders streaming content and stores local session history; per-tab isolation is provided by an `X-Tab-Id` header combined with the session cookie.

## Route Selection
`IntentRouterAgent` selects one of:
- group_access
- sql
- forecasting
- chat
- help
- data_discovery
- knowledge_catalog
- semantica
- data_quality

Notes:
- data_discovery is a specific dataset/table/schema-lookup intent; knowledge_catalog is the default for broader/uncertain data-source, lineage, or policy questions.
- forecasting is a specialist reached from Data Intelligence (`sql` mode) for projection/outlook questions from historical data (`ForecastingAgent`).
- semantica requires an explicit ask for "semantica"/semantic search; otherwise ontology-shaped questions fall through to knowledge_catalog.
- data_quality and group_access are recognized by dedicated heuristics ahead of the general LLM classifier fallback (which defaults to knowledge_catalog when uncertain).
- `agents_registry.yaml` is the enable/disable switch the planner consults per tool_name (help, group_access, data_discovery, sql, forecasting, knowledge_catalog, data_quality, semantica).

## Retrieval Modes
### Data Discovery
- Agent: `DataDiscoveryAgent`
- Source: knowledge catalog vector store
- Filter: metadata repo prefix must start with datasets-
- API: `POST /api/data-discovery/search`

### Knowledge Catalog (PDAP Ontology)
- Primary agent: `KnowledgeCentreRetrieverAgent` — recursive, level-by-level traversal of the `KNOWLEDGE_CATALOG_DIR` Markdown tree (reads each folder's own `index.md`, lets the LLM choose up to 2 sub-targets to descend into, synthesizes from gathered leaf docs). Returns `reply`, `index_files`, `root_files` (no vector chunks).
- Fallback/legacy agent: `KnowledgeCatalogAgent` — FAISS/LanceDB hybrid vector search (BM25-lite + semantic rerank) plus optional graph traversal (`CatalogGraphRagAgent`), used when the catalog directory isn't configured or via the `graph_knowledge_catalog` alias.
- Flags: `HIERARCHICAL_RAG` / `VECTOR_RAG` (`FUNCTIONALITY_FLAGS.yaml`) gate which strategies the supervisor considers.
- API: `POST /api/knowledge-catalog/search`

### Semantica
- Agent bundle under `backend/agents/semantica/` (`knowledge_base.py`, `graph_knowledge_base.py`) — graph-enriched retrieval over indexed workspace content, chunked (~900 chars, 120 overlap), embedded via Azure OpenAI, expanded via a lightweight adjacency graph (2 hops from top seed passages).
- APIs: `POST /api/semantica/search`, `POST /api/semantica/index`, `GET /api/semantica/index/status`

### Data Quality
- Agent: `DataQualityAgent` (`backend/agents/data_quality/`) over a knowledge base of DQ rules/run results (`backend/Data/data_quality/`)
- API: `POST /api/data-quality/search`

## SQL Mode Flow (Data Intelligence)
Standard reasoning:
1. Query is mapped (for example 123456789 -> T001) via `agents/mapping_funs.py`.
2. `SQLSupervisorAgent` resolves conversational references (`query_planner_agent.py`).
3. `NLP2SQLLangGraphAgent` runs pipeline:
   - refresh_volume_metadata
   - select_domains
   - select_tables
   - build_metadata
   - generate_sql
   - validate_sql (score/decision, retries once via regenerate on REWRITE)
4. SQL can be executed by `POST /chat/execute-sql`.
5. Result summary and chart metadata are generated.
6. Final user-facing text is reverse-mapped to real identifiers.

Clean-room reconstruction status through Phase 17:

```text
generate_sql
    |
    v
validate_sql
  | ACCEPT -----------------------> END
  | REJECT -----------------------> END
  ` REWRITE -> regenerate_sql -> validate_sql
```

The maximum rewrite count is 1. Validation is layered: the existing deterministic Phase 4
read-only guard, SQLGlot scope/schema grounding against selected `MetadataRegistry` tables, then a
structured LLM semantic score. Only `ACCEPT` produces `final_sql`; `generated_sql` remains the
latest candidate. The Phase 12 graph itself never executes SQL.

Phase 13 adds the following separate execution path:

```text
Phase 12 final_sql
        |
        v
SQLTokenResolver -> QueryExecutor -> PostgreSQL -> QueryExecutionResult
                                               /                 \
                                  protected summary       ChartMetadataBuilder
                                               \                 /
                                                SQLAnalyticsResult

POST /chat/execute-sql
        |
        v
session cookie + X-Tab-Id
        |
        v
last_generated_sql + last_token_mapping -> SQLExecutionService
```

The endpoint accepts no client-provided SQL and executes only server-owned, per-tab session SQL,
which must originate from an accepted `final_sql`. Known tokens are restored only in SQL literals
at the database boundary. LLM summaries see bounded, privacy-protected previews, while chart
metadata is deterministic. The reconstruction executes PostgreSQL through the Phase 4 read-only
boundary while preserving the source system's Databricks SQL distinction.

Phase 14 adds the Knowledge Catalog specialist without adding the full `/chat` orchestrator:

```text
route=knowledge_catalog
        |
        v
KnowledgeCatalogAgent
        |
        v
KnowledgeCatalogRetriever
     /                 \
hierarchical          hybrid
primary               fallback
                       |
                LanceDB vector + BM25
                       |
                      RRF
     \                 /
        evidence
           |
           v
      LLM grounding
           |
           v
   citation validation
```

The primary path traverses an explicit YAML-front-matter Markdown hierarchy using bounded,
structured `LLMClient` choices. Insufficient leaf evidence falls back to LanceDB's native vector
and full-text search with Reciprocal Rank Fusion. Both paths expose one typed evidence contract.
The request-scoped `POST /api/knowledge-catalog/query` boundary protects the raw question before
retrieval and unmasks only current-request tokens after citation-validated generation. Generated
indexes remain local ignored artifacts. Semantica graph expansion is deferred to Phase 15.

Phase 15 adds three separate specialist paths and configuration-selected Gemini adapters:

```text
Application -> LLMClient ------> GeminiLLMClient (default)
                         `-----> AzureOpenAILLMClient (optional)

LanceDB RAG -> EmbeddingClient -> GeminiEmbeddingClient (default)
                         `-----> AzureOpenAIEmbeddingClient (optional)

data_discovery -> MetadataRegistry -> deterministic matches
data_quality   -> DQ Markdown -> grounded answer -> citation validation
semantica      -> LanceDB hybrid seeds -> adjacency graph -> hops 0..2
                                          -> grounded answer -> citation validation
```

Embedding index manifests bind each managed index to its provider, model or deployment, and vector
dimensions. Incompatible indexes fail before vector search and must be explicitly rebuilt. Data
Discovery uses no LLM or embeddings. Data Quality supplies guidance rather than live profiling.
Semantica uses dedicated 900/120 chunks, a separate `semantica_chunks` table, deterministic graph
edges, visited-set expansion, and bounded evidence. All specialist APIs privacy-process raw input;
the routing supervisor and full `/chat` orchestration remain separate and unchanged.

Phase 16 preserves two separate advanced paths. `ReasoningPromotionPolicy` deterministically keeps
normal specialist execution as `STANDARD` unless the deep-agent flag, confidence threshold,
eligible route, agent registry, and actual approved tool implementation all permit `ADVANCED`.
`AdvancedReasoningPlanner` then runs the bounded provider-neutral
decompose→plan_tools→execute→reflect→synthesize graph with at most one replan and no unrestricted
execution tools.

`MultiHopNLP2SQLAgent` remains a separate Data Intelligence sub-mode. It plans only bounded,
acyclic sub-questions and reuses the standard metadata, generation, Phase 12 validation, token
resolution, and existing read-only `QueryExecutor` for every hop. Per-hop and total row limits plus
a monotonic total timeout are application-enforced. Only protected bounded result previews inform
dependent hops or final summary/table/delta synthesis. Both rollout flags remain disabled by
default. Phase 16 itself adds no full `/chat`, advanced endpoint, forecasting behavior, AWS
resource, or Bedrock adapter; forecasting is implemented separately by Phase 17 below.

Phase 17 adds a separate internal `ForecastingAgent` beneath Data Intelligence. An LLM produces
only a typed metric/frequency/horizon/history-question plan; the existing standard NLP-to-SQL
graph must produce an accepted `final_sql`, and the existing token resolver and bounded read-only
executor acquire exactly one temporal and one numeric aggregate series. Application code rejects
insufficient, future, duplicate, missing, or irregular periods; backtests naive, moving-average,
linear-trend, and eligible seasonal-naive candidates without holdout leakage; selects by MAE then
RMSE then name; refits on all history; and returns calendar-aware projections with approximate
RMSE intervals. Only protected previews reach the explanatory LLM and provider failure has a
deterministic fallback. Individual clinical prediction is rejected. The feature flag remains off
by default, and no public forecasting endpoint, full `/chat`, AWS resource, or Phase 18 behavior
is added. See `docs/forecasting.md` and ADR-017.

Phase 18 adds the React/TypeScript/webpack One UI and the thin `POST /chat` integration boundary.
The backend-owned `ChatOrchestrator` reads the selected session mode, privacy-processes current-turn
input, reuses the supervisor and existing specialists, and returns typed response variants.
Standard SQL remains a two-step flow: `/chat` stores accepted tokenized SQL and the browser invokes
`/chat/execute-sql` without supplying SQL. The frontend uses `HashRouter`, a per-tab
`sessionStorage` identifier sent as `X-Tab-Id`, backend feature flags, and specialist-specific
renderers. Custom context is current-turn only. Group Access is unavailable until a real specialist
exists. Phase 18 adds no Dashboard, authentication, cloud infrastructure, or observability work.
See `docs/decisions/ADR-018-one-ui-chat-orchestration.md`.

Forecasting: `ForecastingAgent` produces projections/outlooks from historical data as its own specialist, reached from the same Data Intelligence surface.

## AI Dashboard (separate tool)
- Agent: `NLP2DashboardAgent` (standard), plus advanced (`nlp2sql_dashboard_agent_advanced.py`) and image-to-dashboard (`nlp2sql_dashboard_agent_image.py`) pipeline variants selectable per-dashboard (`pipeline_mode`: standard/advanced/image).
- Flow: resolve table -> LLM plan (KPIs + charts, or vision-analyzed from a reference image) -> deterministic grid/bbox layout -> parallel per-widget NLP2SQL execution -> persisted `template.json`/`planning.json` under `ARTIFACTS_OUTPUT_DIR/dashboards/<id>/`.
- Supports multi-page dashboards, versioned history/restore, resize/move/rename, CSV/Excel/PDF export, and scheduled refresh — all via `/api/dashboards/*` routes in `server_core/api/routes.py`.
- Frontend: `frontend/pages/AiDashboardPage.tsx`, reachable at `/#/dashboard`.

## Session and Mapping State
Backend session keys include:
- chat_history
- token_mapping_history (per-request only; not persisted across requests — see repo memory for a known scoping caveat)
- last_token_mapping
- last_generated_sql
- follow_up_questions
- custom_context (session-context text sent fresh on every turn, not server-persisted)

Session persistence: hydrated/saved per request via `hydrate_session_from_store`/`persist_session_to_store` to `ARTIFACTS_OUTPUT_DIR/sessions/session_<id>.json` (`chat_service.py`). Multi-tab isolation combines the session cookie with an `X-Tab-Id` header so concurrent tabs never clobber each other's history/mode.

Frontend local storage:
- key: `one_ui_chat_sessions`
- stores One UI session cards, titles, mode, and entries
- key: `ai-dashboard-session` — AI Dashboard chat/template cache (separate from One UI sessions)

## One UI Behavior
- Welcome text is loaded by mode from `CHATBOT_MODE_CONFIG`.
- First mode welcome assistant entry is non-pinnable.
- AI reply pin control is icon-only and shown above avatar.
- Session history supports star, pin list, search, and filters.
- Streaming is applied across assistant, discovery, catalog, and server previews.

## Feature Flags
All backend feature/functionality toggles (UI flags, tool visibility, retrieval strategy, model selection, deep-agent rollout, observability) are defined in `backend/FUNCTIONALITY_FLAGS.yaml`, the single source of truth loaded by `server_core/config/functionality_flags.py` and injected as env vars at startup. Notable groups:
- UI/tool flags: `FOLLOW_UP_QUESTIONS_SHOW`, `CONTEXT_BUTTON`, `CHAT_LATENCY_BADGE`, `KNOWLEDGE_GRAPH_TOOLS_SHOW`, `TOOL_FLAGS` (per-tab/tool visibility served via `GET /api/tool-flags`)
- Retrieval strategy: `HIERARCHICAL_RAG`, `VECTOR_RAG`
- Deep-agent rollout: `DEEP_AGENT_SINGLE_INTENT_ENABLED`, `DEEP_AGENT_MIN_CONFIDENCE`, `DEEP_AGENT_ELIGIBLE_ROUTES`
- Advanced SQL reasoning: `NLP2SQL_MULTIHOP_ENABLED` and related hop/row/timeout limits
- Observability: `OTEL_ENABLED`, `LANGFUSE_ENABLED`, `MLFLOW_ENABLED`, `AGENTOPS_ENABLED`
UI-specific flags are also consumed by `server_core/config/ui_feature_flags.py` and served to the frontend via `GET /api/ui-feature-flags`.

## Primary Endpoints
- `POST /chat`, `POST /chat/reset`, `POST /chat/select-mode`, `POST /chat/execute-sql`
- `GET /api/chat-mode/welcome`
- `POST /api/data-discovery/search` (source), `POST /api/data-discovery/query` (reconstruction)
- `POST /api/knowledge-catalog/search` (source architecture), `POST /api/knowledge-catalog/query`
  (Phase 14 reconstruction)
- `POST /api/semantica/search`, `POST /api/semantica/index`, `GET /api/semantica/index/status`
  (source), `POST /api/semantica/query` (reconstruction)
- `POST /api/data-quality/search` (source), `POST /api/data-quality/query` (reconstruction)
- `POST /api/dashboards/generate`, `GET /api/dashboards`, `GET /api/dashboards/<id>`, plus per-dashboard/-widget resize, move, rename, export (csv/excel/pdf), schedule-refresh, and version history/restore routes
- `POST /api/feedback`, `POST /api/schedule-report`, `POST /api/custom-context`
- `GET /api/health`, `GET /api/ui-feature-flags`, `GET /api/tool-flags`

Note: the older `POST /api/knowledge-catalog/graph-rag/search` / `.../rebuild` handler functions still exist in `routes.py` but currently have no `@bp` route decorator registering them — they are not reachable over HTTP. Graph-based catalog retrieval (`CatalogGraphRagAgent`) is only used today as an internal fallback inside the `knowledge_catalog` flow, not as its own endpoint.

## Knowledge Catalog Configuration
Set this backend environment variable to point the catalog agents at the Markdown tree:

```text
KNOWLEDGE_CATALOG_DIR=C:\path\to\knowledge-catalog
```

Restart the backend after changing this value. `KnowledgeCentreRetrieverAgent` reads the tree directly on each query (no rebuild step); the legacy `CatalogGraphRagAgent`'s graph/hierarchy caches (`vector_stores/catalog_graph.json`, `vector_stores/catalog_hierarchy.json`) rebuild on demand or after a 12-hour TTL, but that agent is currently only reachable as an internal fallback (see Primary Endpoints note above), not via its own HTTP endpoint.

## Runbook
### Backend
```powershell
cd backend
python app.py
```
Uvicorn does not hot-reload agent module edits by default in this repo (`FASTAPI_RELOAD` env var controls it) — restart the process after backend code changes.

### Frontend
```powershell
npm install
npm run dev
```
HashRouter app — browse to `http://localhost:5173/#/...` (a bare `/path` without the `#` will not resolve).

### Health Check
```powershell
curl http://localhost:8000/api/health
```
