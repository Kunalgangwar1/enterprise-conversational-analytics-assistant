# Multi-hop NLP-to-SQL

`MultiHopNLP2SQLAgent` is a SQL-specific advanced mode, separate from the generic specialist-tool
planner. Standard NLP-to-SQL remains the default for ordinary questions. Multi-hop is intended for
bounded dependent analytics such as finding a leading facility type and then comparing its paid
amount with other types. Forecasting requests are handled by the separate Phase 17 specialist.

## Workflow

```text
privacy-safe question
  -> structured hop plan
  -> validate count, IDs, dependencies, acyclic order, and no planner SQL
  -> standard NLP2SQLAgent for each hop
  -> require Phase 12 ACCEPT/final_sql
  -> current-request token resolution at the execution boundary
  -> BudgetedQueryExecutor -> existing QueryExecutor
  -> bounded privacy-protected result preview
  -> next dependent hop
  -> structured synthesis -> deterministic Markdown rendering
```

The LangGraph has explicit `plan`, `execute_hop`, `check_budget_and_remaining`,
`prepare_next_hop`, and `synthesize` nodes. It advances one hop per graph iteration rather than
hiding an unbounded loop in a node. Planner output contains sub-questions and dependencies, never
SQL. Every hop reuses the existing metadata selection, generation, read-only/schema/semantic
validation, token resolver, and PostgreSQL query executor. No second engine, credential, SQL
generator, parser, or direct Psycopg path exists.

## Enforced budgets

The existing functionality flags define defaults of three hops, 100 rows per hop, 250 rows total,
and 20 seconds total. `MultiHopBudget` enforces them with a monotonic clock. Before every hop it
checks remaining hop, row, and time capacity; the query receives the smaller of the existing global
executor limit and the remaining multi-hop allowance. Budget exhaustion raises a controlled error
and no dependent SQL starts. The PostgreSQL executor's optional per-call overrides can only tighten
its constructor limits.

## Privacy and synthesis

Database rows never go directly to an LLM. `SQLSummaryPreviewBuilder` serializes bounded rows,
reuses known current-request `Txxx` mappings, and redacts email and phone values. Only that protected
preview can enter a dependent hop or final synthesis. The returned Markdown is unmasked only with
the current request mapping; unknown tokens remain protected and category placeholders stay
redacted.

Synthesis returns a typed summary, table, and delta annotations. Application code renders the table
and filters unsupported delta values against numeric comparisons derivable from completed protected
results. Failed generation, non-`ACCEPT` validation, unresolved tokens, query timeouts, database
failures, provider failures, and budget exhaustion stop dependent work rather than fabricating a
complete conclusion.

The source architecture used Databricks SQL. This reconstruction deliberately reuses its local
PostgreSQL read-only boundary. A configured internal live smoke is available with:

```bash
python -m app.nlp2sql.multihop.smoke \
  "Find the facility type with the highest claim volume, then compare its average paid amount."
```

It requires the existing rollout flag, provider, metadata database, and read-only query settings.
Normal tests use fakes and require no Gemini, Azure, or AWS credentials.
