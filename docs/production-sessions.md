# Production session storage

Phase 22 adds a clean-room Redis production extension behind the existing `SessionStore` boundary.
The architecture source describes file-backed JSON session state; `JsonFileSessionStore` therefore
remains the default and the faithful local reconstruction. Redis is an explicitly documented
deployment extension for multiple workers or hosts, not a silent change to the source architecture.

## Backends

Set `SESSION_STORE_BACKEND` to one of:

- `json` (default): atomic local files under `ARTIFACTS_OUTPUT_DIR/sessions`; suited to local learning
  and a single application process.
- `redis`: shared synchronous redis-py storage; suited to multiple application replicas.

Redis is selected only at application construction. Creating settings or starting with the JSON
backend does not connect to Redis. When Redis is selected, `SESSION_REDIS_URL` is required and the
application does not fall back to local files during an outage. This fail-closed behavior prevents
replicas from diverging into different conversation histories.

## Configuration

```dotenv
SESSION_STORE_BACKEND=redis
SESSION_REDIS_URL=redis://:replace_with_secret@redis.internal:6379/0
SESSION_REDIS_KEY_PREFIX=eca:session
SESSION_REDIS_MAX_UPDATE_RETRIES=5
SESSION_MAX_AGE_SECONDS=86400
```

Keep the URL in an environment secret or secret manager, never in source control. The Redis expiry
reuses `SESSION_MAX_AGE_SECONDS`, so the server-side state lifetime and browser cookie lifetime have
one configuration source. Every successful save or atomic update refreshes the expiry.

## Data format and keys

Redis values are UTF-8 JSON validated by Pydantic:

```json
{"schema_version":1,"state":{"browser_session_id":"...","tab_id":"..."}}
```

The full state includes the authenticated owner and conversation fields documented in
[`sessions.md`](sessions.md). Pickle and executable serialization formats are not accepted.
Malformed documents, unknown schema versions, and identity mismatches are rejected rather than
silently reset or overwritten.

Keys have the shape `eca:session:<sha256>`. The digest reuses the established length-delimited
subject + browser UUID + tab identity derivation. Raw subjects, browser identifiers, and tab names
never appear in the Redis key.

`custom_context` and `token_mapping_history` are deliberately absent. Only the latest validated SQL
and current token mapping needed by the explicit execution workflow are persisted.

## Concurrency and failure behavior

Each mutation uses Redis `WATCH`, reads and validates the current document, computes a complete new
`SessionState`, then uses `MULTI`, `SET ... EX`, and `EXEC`. A changed key causes a bounded retry.
Exhausting `SESSION_REDIS_MAX_UPDATE_RETRIES` returns a sanitized HTTP `409 session_conflict`.

Redis connection/command failures return `503 session_store_unavailable`. Corrupt state returns the
existing sanitized storage error. Responses never expose the Redis URL, credentials, host details,
or raw payload. Reset affects only the current authenticated subject/browser/tab key.

## Connection lifecycle

The application creates one synchronous redis-py client for the selected store. redis-py manages
its connection pool and connects lazily on the first command. FastAPI lifespan shutdown closes the
client/pool. The synchronous client is intentional because the current FastAPI route and session
call graph is synchronous.

## Optional local smoke check

Automated tests use a deterministic in-memory test double and require no Redis server, Docker,
network, Gemini, Azure OpenAI, or AWS. A developer who already has a disposable Redis instance may
run an application smoke check by setting the variables above, starting the API, selecting a mode,
and inspecting only the configured key prefix with `redis-cli --scan --pattern 'eca:session:*'`.
Do not use production credentials or real user/patient/member data for this check.

Useful operational signals include rates of `session_conflict`, `session_store_unavailable`, corrupt
payload errors, Redis command latency, connection-pool saturation, memory usage, and key eviction.
Back up Redis only if session recovery is an explicit product requirement; sessions are bounded,
expiring operational state rather than the system of record.
