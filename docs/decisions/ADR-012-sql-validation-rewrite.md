# ADR-012: Layered SQL validation with one controlled rewrite

## Status

Accepted

## Context

LLM-generated SQL is untrusted. A candidate may be structurally unsafe, reference hallucinated
schema, or be read-only and syntactically valid while still answering the analytical question
incorrectly. The Phase 11 generation prompt provides useful grounding but is not a security or
correctness boundary.

The source workflow validates generated SQL and may regenerate it once. The source production
engine is Databricks SQL, while this reconstruction currently targets local PostgreSQL.

## Decision

Validate each candidate in three ordered layers:

1. reuse the existing Phase 4 SQLGlot read-only guard;
2. use SQLGlot AST scopes to validate physical tables, aliases, CTEs, and deterministically
   resolvable columns against selected tables and `MetadataRegistry`;
3. request a provider-neutral, structured LLM semantic assessment only after both deterministic
   layers pass.

Application policy converts the model's bounded score into `ACCEPT`, `REWRITE`, or `REJECT` using
environment-backed thresholds. The model does not return or control the workflow decision.
Deterministic safety failures override every semantic score.

`REWRITE` follows an explicit LangGraph edge to `regenerate_sql`, which reuses the same safe
question, selected domains, selected tables, and metadata context plus concise findings. It does
not reopen metadata selection. Exactly one rewrite is allowed, and a second rewrite outcome is
converted to terminal `REJECT` with `rewrite_budget_exhausted`.

Only `ACCEPT` populates `final_sql`. The latest candidate remains available separately as
`generated_sql`. Neither value is executed in Phase 12.

## Alternatives considered

- Execute generated SQL immediately: rejected because generation is not an execution boundary.
- Rely only on the read-only parser: rejected because syntax safety does not catch schema
  hallucinations or semantic errors.
- Rely only on an LLM judge: rejected because model judgment cannot enforce deterministic safety.
- Retry until the model succeeds: rejected because it is unbounded and can create unpredictable
  cost and latency.
- Repeat domain and table selection on every rewrite: rejected because this phase calls for a
  bounded correction within the already selected schema; broader replanning belongs to later
  reasoning phases.

## Consequences

- Unsafe SQL cannot be accepted solely by model judgment.
- Schema hallucinations and common ambiguous references are caught deterministically.
- Semantic correctness receives a focused assessment grounded in table grain and metadata notes.
- At most one extra generation and one extra semantic call bound incremental cost and latency.
- Semantic scoring remains model-dependent.
- Some valid, unusually complex SQL may require future scope-validator improvements.
- Database execution, result summarization, and presentation remain deferred to Phase 13.
