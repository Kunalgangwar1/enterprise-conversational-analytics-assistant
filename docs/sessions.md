# Sessions and conversation state

Phase 7 established typed durable state, Phase 21 bound it to authenticated ownership, and Phase 22
adds an optional shared Redis backend. See [Production sessions](production-sessions.md) for
configuration and operations.

## Logical session identity

A logical conversation is the combination of three identifiers:

- The normalized authenticated subject.
- An opaque UUID4 browser-session ID stored in the `eca_session_id` cookie by default.
- A tab ID supplied in the configurable `X-Tab-Id` request header.

The browser cookie contains only its opaque identifier. It is `HttpOnly`, uses `SameSite=lax`, has
a configurable maximum age, and uses the `Secure` flag when `SESSION_COOKIE_SECURE` is enabled.
Missing or malformed cookie values are replaced with a newly generated UUID4 rather than being used
as storage identifiers.

The tab header defaults to `default` when absent. Supplied values must be 1-64 characters and use a
small allowed character set. A SHA-256 digest derived from all three validated identifiers determines the
storage key, so no raw identity value is concatenated into a filename or Redis key.

This combination isolates concurrent tabs within the same browser:

```text
subject A + browser session + tab-a -> one persisted conversation
subject A + browser session + tab-b -> a separate persisted conversation
subject B + browser session + tab-a -> a third persisted conversation
```

## Persisted state

Each session JSON document contains:

- `browser_session_id`
- `tab_id`
- `owner_subject`
- `selected_mode`, defaulting to `auto`
- `chat_history`, initially empty
- `last_generated_sql`, initially `null`
- `last_token_mapping`, initially `null`
- `follow_up_questions`, initially empty
- timezone-aware UTC `created_at` and `updated_at` timestamps

The message contract currently permits only `user` and `assistant` roles. No speculative agent or
tool traces are modeled.

Two important values are deliberately not persisted:

- `token_mapping_history` is request-scoped and remains outside `SessionState`.
- `custom_context` will arrive fresh with a future chat turn rather than becoming durable backend
  session memory.

The current chat service persists only the latest accepted SQL mapping required for explicit query
execution. No mapping history is created, and custom context remains current-turn only.

## Storage behavior

`SessionService` depends on the `SessionStore` contract rather than filesystem operations. Its
state-changing operations use the store's atomic update primitive.
`JsonFileSessionStore` writes generated files under `backend/artifacts/sessions/` by default. It
serializes and validates state with Pydantic, reports corrupted JSON as `SessionStoreError`, and
refuses to silently overwrite a corrupted existing document.

Writes go to a complete temporary file in the same directory, are flushed, and are atomically moved
over the destination. A process-local reentrant lock protects read-modify-write operations within
one application process. This lock does not coordinate multiple worker processes or hosts.

JSON persistence is the source-described, default local backend and remains convenient for learning
and inspection. The clean-room `RedisSessionStore` extension is intended for horizontally scaled
production deployments. It shares versioned JSON state across workers, applies expiry, and uses
Redis optimistic transactions to prevent silent lost updates. There is no Redis-to-file fallback.

Authenticated requests never resolve legacy pre-Phase-21 two-part storage keys. This intentionally
resets old local demo conversations rather than risking cross-user disclosure. On every new-format
load, the stored owner must match the subject used to derive the path. This prevents history,
`last_generated_sql`, token mappings, and follow-ups from crossing users even if browser cookie and
tab ID are identical.

## Reset behavior

`POST /chat/reset` clears:

- chat history
- last generated SQL
- last token mapping
- follow-up questions

It preserves the owner subject, browser-session ID, tab ID, selected mode, and creation timestamp, then updates
`updated_at`. Preserving the selected mode is an explicit clean-room decision because the source
runbook does not fully define reset semantics.
