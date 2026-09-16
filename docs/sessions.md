# Sessions and conversation state

Phase 7 establishes typed durable state for future conversational follow-ups without implementing
the chat pipeline itself.

## Logical session identity

A logical conversation is the combination of two identifiers:

- An opaque UUID4 browser-session ID stored in the `eca_session_id` cookie by default.
- A tab ID supplied in the configurable `X-Tab-Id` request header.

The browser cookie contains only its opaque identifier. It is `HttpOnly`, uses `SameSite=lax`, has
a configurable maximum age, and uses the `Secure` flag when `SESSION_COOKIE_SECURE` is enabled.
Missing or malformed cookie values are replaced with a newly generated UUID4 rather than being used
as storage identifiers.

The tab header defaults to `default` when absent. Supplied values must be 1-64 characters and use a
small allowed character set. A SHA-256 digest derived from both validated identifiers determines the
session filename, so neither raw value is concatenated into a filesystem path.

This combination isolates concurrent tabs within the same browser:

```text
browser session + tab-a -> one persisted conversation
browser session + tab-b -> a separate persisted conversation
```

## Persisted state

Each session JSON document contains:

- `browser_session_id`
- `tab_id`
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

Phase 9's independent privacy package can produce a serializable current-request mapping for a
future chat service to assign to `last_token_mapping`, but it does not load or mutate sessions.
No mapping history is created. Custom-context handling and `POST /chat` remain unimplemented.

## Storage behavior

`SessionService` depends on the `SessionStore` contract rather than filesystem operations.
`JsonFileSessionStore` writes generated files under `backend/artifacts/sessions/` by default. It
serializes and validates state with Pydantic, reports corrupted JSON as `SessionStoreError`, and
refuses to silently overwrite a corrupted existing document.

Writes go to a complete temporary file in the same directory, are flushed, and are atomically moved
over the destination. A process-local reentrant lock protects read-modify-write operations within
one application process. This lock does not coordinate multiple worker processes or hosts.

JSON persistence is faithful to the reconstruction architecture and convenient for local learning
and inspection. It is not the final horizontally scalable production session solution. Shared
production state and distributed locking remain later-phase work.

## Reset behavior

`POST /chat/reset` clears:

- chat history
- last generated SQL
- last token mapping
- follow-up questions

It preserves the browser-session ID, tab ID, selected mode, and creation timestamp, then updates
`updated_at`. Preserving the selected mode is an explicit clean-room decision because the source
runbook does not fully define reset semantics.
