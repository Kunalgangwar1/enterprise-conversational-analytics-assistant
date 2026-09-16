# ADR-013: Accepted SQL execution and privacy-safe analytical results

## Status

Accepted

## Context

Validated SQL must be executed safely and converted from raw database rows into a bounded,
UI-friendly analytical result. Tokenized SQL may need original synthetic identifiers at the
database boundary, while returned rows can contain identifiers and generic PII that must not be
sent raw to an LLM. Summary availability should not determine whether a successful database result
can be returned.

## Decision

- Execute only non-empty Phase 12 `final_sql` with decision `ACCEPT`.
- Restore current privacy tokens only in exact SQL string literals through a SQLGlot AST
  transformation at the database boundary.
- Route every database query through the existing Phase 4 `QueryExecutor`, preserving its safety,
  timeout, row-limit, and truncation behavior.
- Summarize only a bounded preview after reusing current tokens and applying the existing Phase 9
  privacy processor.
- Restore only current known tokens in successful summaries and use deterministic text for empty
  results or model failures.
- Infer basic chart metadata deterministically from actual returned values.
- Expose `POST /chat/execute-sql` using server-side per-tab session SQL and mapping, with no
  client-provided SQL field.
- Never return or log resolved SQL, raw summary previews, row contents, or privacy mappings.

The Phase 13 execution service is separate from the Phase 12 LangGraph. Future chat orchestration
must populate `SessionState.last_generated_sql` only from accepted `final_sql`.

## Alternatives considered

- Execute SQL immediately in LangGraph: rejected to preserve separation between generation,
  validation, session orchestration, and an explicit user-triggered execution endpoint.
- Accept arbitrary SQL over HTTP: rejected because it would turn the endpoint into a general query
  interface and bypass accepted server state.
- Send the complete query result to the LLM: rejected because it increases privacy exposure, cost,
  and prompt size and ignores existing result bounds.
- Use an LLM for chart selection: rejected because the initial supported chart rules are simple and
  deterministic.
- Fail the complete request when summarization fails: rejected because valid bounded rows remain
  useful and can be described deterministically.
- Return resolved SQL to the browser: rejected because restored literals can contain original
  identifiers.

## Consequences

- Execution has both an accepted-SQL gate and Phase 4 defense in depth.
- Original identifiers exist only at the narrow database execution boundary.
- The LLM sees less sensitive, bounded result data.
- Results remain available during summary-provider outages.
- Chart metadata is predictable and testable without a model.
- The endpoint depends on server-side accepted SQL being populated by later chat orchestration.
- The source system remains Databricks SQL; local PostgreSQL remains a reconstruction substitute.
