# SQL execution and analytical results

Phase 13 converts accepted Phase 12 SQL into a bounded, UI-neutral analytical result. The source
system executes Databricks SQL. This reconstruction uses the Phase 4 PostgreSQL `QueryExecutor` as
its local substitute and does not present PostgreSQL as the original production engine.

## Execution boundary

Normal service execution requires both:

- a non-empty Phase 12 `final_sql`;
- `SQLValidationDecision.ACCEPT`.

`generated_sql` is never used as a fallback. `REWRITE`, `REJECT`, and missing final SQL raise
`SQLNotValidatedError` before the executor is called. Even a manually constructed accepted object
does not bypass Phase 4: `QueryExecutor` validates the SQL again, opens a read-only transaction,
sets the statement timeout, and bounds fetched rows.

All database access goes through `QueryExecutor`. Phase 13 creates no separate engine, direct
Psycopg call, safety parser, `EXPLAIN`, or count query.

## Privacy-token restoration

Phase 9 may turn a synthetic business identifier such as `M000245` into `T001`, leaving accepted
SQL with a predicate such as `member_external_id = 'T001'`. `SQLTokenResolver` parses PostgreSQL
with SQLGlot and replaces only exact string-literal nodes whose token exists in the current typed
mapping. Aliases, identifiers, comments, token substrings, and arbitrary text are not replaced.

An exact token-like literal without a current mapping fails closed. Resolved SQL may contain an
original identifier, so it is passed only to `QueryExecutor`; it is not logged, returned by the
API, or placed in an LLM prompt. Persisted session dictionaries are validated and adapted back to
the Phase 9 `TokenMappingEntry` representation.

## Bounded result contract

`SQLAnalyticsResult` contains:

- columns and structured row mappings;
- returned `row_count` and `truncated` exactly as supplied by `QueryExecutionResult`;
- execution elapsed milliseconds;
- a concise summary and its source;
- deterministic chart metadata.

`QUERY_MAX_ROWS` remains the database fetch boundary. Phase 13 does not issue an expensive count to
discover a complete result size. When `truncated=true`, both the response and summary input retain
that fact.

## Privacy-safe summarization

The summarizer copies at most `SQL_RESULT_SUMMARY_MAX_ROWS` rows, serializes common database values
including `Decimal`, `date`, `datetime`, `None`, numbers, strings, and booleans, and caps the final
preview at `SQL_RESULT_SUMMARY_MAX_CHARS`. These settings default to 50 rows and 12,000 characters
and are independent of `QUERY_MAX_ROWS`.

Before an LLM sees the preview, current original identifiers are restored to their existing tokens
where possible. The existing `PrivacyProcessor` then tokenizes other supported business identifiers
and redacts email addresses and phone numbers. Actual returned rows are not mutated. After a
successful structured summary, `ResponseUnmasker` restores only tokens in the current mapping;
new tokens and `[EMAIL]` or `[PHONE]` remain protected.

Zero rows produce `No rows matched the query.` without an LLM call. Provider configuration,
authentication, timeout, rate-limit, provider, or structured-output failure produces a concise
deterministic fallback. A successful database result is never discarded solely because summary
generation is unavailable.

No row contents, preview, prompt, mapping, original identifier, email, phone number, or resolved SQL
is logged. Completion logging contains only row count, elapsed time, and truncation.

## Deterministic chart metadata

`ChartMetadataBuilder` inspects actual non-null Python values and applies conservative rules:

1. no rows produces `table`;
2. temporal plus meaningful numeric columns produces `line`;
3. categorical plus meaningful numeric columns produces `bar`;
4. two meaningful numeric columns may produce `scatter`;
5. uncertain or mixed data produces `table`.

Numeric columns named `id` or ending in `_id` are not treated as measures. Multiple numeric metrics
may share the categorical or temporal axis. Titles are derived deterministically from selected
column names. The backend returns recommendations only and renders no chart.

## `POST /chat/execute-sql`

The endpoint has no request-body SQL field. It uses the browser session cookie plus `X-Tab-Id` to
load only that tab's `last_generated_sql` and `last_token_mapping`. This preserves Phase 7 tab
isolation and prevents a client from using the endpoint as an arbitrary SQL interface.

The invariant is that `last_generated_sql` is server-owned and may only be populated from Phase 12
`final_sql` after `ACCEPT`. The complete `/chat` flow that performs this write is intentionally not
implemented yet. Until then, a session without accepted SQL receives HTTP 409 `no_validated_sql`.

Other controlled errors include:

- HTTP 409 `sql_token_resolution_failed` for missing or invalid token mappings;
- HTTP 409 `sql_execution_rejected` when the Phase 4 safety guard rejects stored SQL;
- HTTP 504 `query_timeout` for statement timeout;
- HTTP 503 `query_execution_unavailable` when execution is not configured;
- HTTP 500 `query_execution_failed` for sanitized database failures.

Responses never contain SQL, database credentials, or privacy mappings.
