# Backend API

The backend uses a central FastAPI application contract and route composition. Informational APIs
are mounted below `/api`; stateful conversation-control endpoints use `/chat`. The OpenAPI UI is
available at `/docs` when the development server is running.

## Implemented endpoints

### `GET /api/health`

Reports process availability, application name, and configured environment. This is a process
health check; it does not connect to PostgreSQL or verify downstream services.

### `GET /api/ui-feature-flags`

Returns the frontend-safe subset of UI visibility flags from the validated functionality-flag
configuration.

### `GET /api/tool-flags`

Returns configured specialist-tool availability. Tool flags and chat-mode contracts are separate:
a named product mode does not imply that a future tool or agent is implemented or enabled.

### `GET /api/chat-mode/welcome?mode={mode}`

Returns static, typed welcome information for one canonical top-level mode. Supported mode values
are:

- `auto`
- `sql`
- `group_access`
- `data_discovery`
- `knowledge_catalog`
- `semantica`
- `data_quality`

Example response:

```json
{
  "mode": "sql",
  "display_name": "Data Intelligence",
  "description": "A future mode for exploring governed enterprise data with natural language.",
  "welcome_message": "This mode is intended for natural-language questions about governed analytical data."
}
```

Unsupported supplied modes return HTTP 400 using the application error envelope:

```json
{
  "error": {
    "code": "invalid_chat_mode",
    "message": "Unsupported chat mode: magic_ai"
  }
}
```

Missing or structurally invalid request parameters continue to use FastAPI's normal validation
behavior. Unknown values never fall back to `auto`. Historical aliases are intentionally omitted
because this clean-room reconstruction has no deployed legacy clients. Forecasting is an internal
specialist capability selected through Data Intelligence rather than a top-level user mode.

## Request flow

```text
HTTP request
    ↓
FastAPI route
    ↓
ChatModeService
    ↓
immutable ChatModeRegistry
    ↓
typed response
```

The welcome path uses static application configuration only. It does not instantiate a database
engine, query executor, metadata registry, session store, or LLM client.

### `POST /chat/select-mode`

Selects and persists a canonical mode for the current browser-session/tab pair.

```json
{
  "mode": "sql"
}
```

Successful response:

```json
{
  "mode": "sql",
  "display_name": "Data Intelligence"
}
```

The endpoint creates the opaque browser-session cookie when it is missing or malformed and reads
the tab identifier from `X-Tab-Id`, defaulting to `default` when the header is absent. Unsupported
modes return the existing `invalid_chat_mode` error envelope. No agent is executed.

### `POST /chat/reset`

Clears conversational fields for the current browser-session/tab pair while preserving its selected
mode. A successful response is:

```json
{
  "status": "reset",
  "mode": "sql"
}
```

Reset does not affect another tab with the same browser-session cookie.

### `POST /chat`

Executes one conversational turn using the selected mode stored for the current cookie and
`X-Tab-Id` pair. It accepts no arbitrary internal route:

```json
{
  "message": "Show monthly encounter volume",
  "sql_strategy": "standard",
  "custom_context": "Use the last completed calendar year."
}
```

`sql_strategy` is limited to `auto`, `standard`, `advanced`, or `forecasting` and applies only to
the `sql` mode. Custom context is bounded, privacy-processed, and used for this turn only; it is
never persisted. Responses use a typed `response_type` discriminator for messages, standard SQL,
advanced results, forecasts, discovery, or grounded retrieval output.

Standard SQL generation returns accepted privacy-tokenized SQL and stores it server-side without
executing it. The browser can subsequently call `POST /chat/execute-sql` with no SQL body. That
endpoint loads the current tab's accepted SQL and token mapping and retains the Phase 13
read-only-execution boundary.

Group Access returns a controlled `specialist_unavailable` error until a real specialist is
implemented. LLM-backed modes return safe provider/configuration errors; deterministic chat/help
and Data Discovery do not require model or cloud credentials.

### Phase 15 specialist queries

- `POST /api/data-discovery/query` returns deterministic dataset metadata matches.
- `POST /api/data-quality/query` returns grounded guidance and safe citations.
- `POST /api/semantica/query` returns graph-expanded grounded answers and safe citations.

All accept a required non-blank `question`. The API layer privacy-processes input. Responses do not
contain vectors, adjacency data, AI configuration, provider payloads, privacy mappings, or database
rows. These request-scoped endpoints do not require sessions and do not implement conversational
follow-up state.

## Not implemented

`POST /api/custom-context` is not implemented. Phase 18 supplies context in the current `POST /chat`
request instead, without durable storage. Dashboard, authentication, and production-cloud APIs
remain outside this phase.
