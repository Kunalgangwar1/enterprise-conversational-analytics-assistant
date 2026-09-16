# Standard NLP-to-SQL, validation, and result execution

Phases 11–13 implement metadata-grounded SQL generation, layered validation, one bounded
correction attempt, and a separate accepted-SQL execution service. The documented source
architecture targets Databricks SQL; this clean-room learning reconstruction generates, validates,
and executes PostgreSQL-compatible SQL against the local synthetic database.

## Pipeline

The compiled LangGraph has seven application nodes:

```text
START
  -> refresh_metadata
  -> select_domains
  -> select_tables
  -> build_metadata
  -> generate_sql
  -> validate_sql
       | ACCEPT -> END
       | REJECT -> END
       ` REWRITE -> regenerate_sql -> validate_sql
```

`validate_sql` uses conditional graph edges. It does not hide a retry loop inside a node.
`regenerate_sql` can run at most once, so the second validation always terminates as `ACCEPT` or
`REJECT`. Metadata refresh, domain selection, table selection, and context construction are not
repeated during a rewrite.

A direct semantic validation path makes four structured LLM calls: domain selection, table
selection, SQL generation, and semantic assessment. A semantic rewrite followed by assessment of
the corrected query makes six. Deterministic failures skip semantic calls that cannot add value.

## Inputs and state

`NLP2SQLAgent.generate_sql()` accepts only a `safe_question`; callers remain responsible for
running `PrivacyProcessor` first. State contains the privacy-safe question, selected metadata,
current and previous SQL candidates, concise validation findings, attempt counters, and the final
accepted SQL. It contains no raw privacy mapping, credentials, database rows, or session objects.

Initial generation sets `generation_attempt=1` and `rewrite_count=0`. Regeneration sets
`generation_attempt=2` and `rewrite_count=1`. `NLP2SQL_MAX_REWRITES` is currently constrained to
exactly 1 to match the source workflow.

## Layered validation

Validation runs in a fixed order. A later layer cannot override an earlier failure.

### 1. Structural and read-only safety

The validator reuses the Phase 4 `validate_read_only_sql()` boundary. That SQLGlot guard remains
the single source of truth for blank or malformed SQL, multiple statements, non-query statements,
mutations, DDL, commands, `SELECT INTO`, and locking queries. Phase 12 does not duplicate the
guard's forbidden AST node list.

Mutating, multi-statement, DDL, command, `SELECT INTO`, and locking SQL receives an immediate hard
`REJECT`. It is never sent to the semantic assessor. A parser failure that looks like a generation
defect receives `REWRITE` on attempt one and `REJECT` after the rewrite budget is exhausted.

### 2. Schema grounding

`SchemaGroundingValidator` uses SQLGlot scopes and AST nodes, not regular expressions. It resolves
physical tables, table aliases, CTEs, derived scopes, CTE output aliases, and straightforward
qualified and unqualified columns against the selected table set and the injected Phase 5
`MetadataRegistry`.

Unknown physical tables, tables outside `selected_tables`, unknown columns, unresolved qualifiers,
and ambiguous unqualified columns receive deterministic findings and `REWRITE` on the first
attempt. A second such failure becomes `REJECT`. CTE names are scope sources rather than physical
tables, and selected bridge tables remain valid; for example, a query may join
`claims -> providers -> facilities` when all three were selected.

Schema failures do not call the semantic model. Rewrite guidance directs generation back to the
same selected physical tables and documented columns.

### 3. Semantic assessment

Only structurally safe, schema-grounded SQL reaches `SemanticSQLValidator`. It calls the injected,
provider-neutral `LLMClient` with a strict `SQLSemanticAssessment` Pydantic response containing:

- a score in `[0, 1]`;
- concise issues;
- optional correction guidance.

The request supplies the privacy-safe question as user content and keeps validation rules,
selected domains and tables, metadata context, and the SQL candidate in separate system content.
It asks about measures, dimensions, filters, aggregation, grouping, joins, table grain,
double-counting risk, temporal meaning, ordering, and top-N intent. It asks for no execution,
schema changes, invented semantics, workflow decision, or chain-of-thought.

Provider timeouts, authentication failures, rate limits, invalid structured output, and other
provider failures raise a controlled NLP-to-SQL validation exception. They never fabricate an
acceptance.

## Score policy and result contract

Application code—not the model—maps the semantic score to a decision:

```text
score >= NLP2SQL_ACCEPT_SCORE (default 0.80)   -> ACCEPT
score >= NLP2SQL_REWRITE_SCORE (default 0.50) -> REWRITE
otherwise                                    -> REJECT
```

Configuration enforces
`0 <= NLP2SQL_REWRITE_SCORE < NLP2SQL_ACCEPT_SCORE <= 1`. A semantic `REWRITE` on the second
validation becomes `REJECT` with `reason_code="rewrite_budget_exhausted"`; there is no third SQL
generation.

`generated_sql` is always the latest candidate. `final_sql` is populated only after `ACCEPT` and
then equals `generated_sql`. Both `REWRITE` and `REJECT` leave `final_sql=None`. Phase 13 relies on
that distinction at its execution boundary.

## Outcome examples

Direct acceptance:

```text
generate valid SQL -> deterministic checks pass -> semantic score 0.95 -> ACCEPT
final_sql = generated_sql; generation_attempt = 1; rewrite_count = 0
```

Corrected acceptance:

```text
generate schema-valid but semantically incomplete SQL -> score 0.65 -> REWRITE
regenerate within the same selected schema -> score 0.95 -> ACCEPT
final_sql = corrected SQL; generation_attempt = 2; rewrite_count = 1
```

Hard rejection:

```text
generate DELETE or SELECT + DROP -> Phase 4 guard fails -> REJECT
no semantic call; no rewrite; final_sql = None
```

Rewrite budget exhausted:

```text
first score 0.60 -> REWRITE -> second score 0.60 -> REJECT
reason_code = rewrite_budget_exhausted; final_sql = None
```

## Accepted result execution

The Phase 12 LangGraph still performs no database execution. A separate Phase 13
`SQLExecutionService` accepts only a non-empty `final_sql` with decision `ACCEPT`. It restores known
privacy tokens only in exact SQL string literals, delegates all database access to the existing
Phase 4 `QueryExecutor`, and returns its bounded rows and truncation status unchanged.

```text
Phase 12 ACCEPT final_sql
  -> SQLTokenResolver
  -> QueryExecutor
  -> QueryExecutionResult
  -> privacy-safe bounded summary + deterministic ChartMetadata
  -> SQLAnalyticsResult
```

`POST /chat/execute-sql` accepts no client SQL. It resolves the session cookie and `X-Tab-Id`, loads
that tab's server-owned `last_generated_sql` and `last_token_mapping`, and invokes the service. The
field must only be populated from an accepted Phase 12 `final_sql`; the future complete `/chat`
orchestration will own that write.

Result summarization sends at most `SQL_RESULT_SUMMARY_MAX_ROWS` and
`SQL_RESULT_SUMMARY_MAX_CHARS` of privacy-protected preview data to the provider-neutral LLM. Empty
results and unavailable summary providers use deterministic text. Basic table, bar, line, and
scatter metadata is selected from actual returned Python values without another model call. See
[`sql-results.md`](sql-results.md) for the complete execution contract.

## Phase 16 multi-hop reuse

Phase 16 adds an internal, feature-gated `MultiHopNLP2SQLAgent`. It plans only sub-questions and
dependencies; each hop calls this same standard pipeline and requires an `ACCEPT/final_sql` before
using the existing executor with stricter row/time limits. Protected bounded result previews may
inform dependent hops. It adds no arbitrary-SQL endpoint and no full `POST /chat` orchestration.
See [`multihop-nlp2sql.md`](multihop-nlp2sql.md).
