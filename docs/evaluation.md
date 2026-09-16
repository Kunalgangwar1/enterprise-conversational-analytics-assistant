# Evaluation and regression framework

The Phase 20 evaluator is a sidecar to the application, not part of the HTTP request path. It runs
versioned synthetic golden cases through existing product boundaries and writes a machine-readable
`report.json` plus a study-friendly `summary.md` under `backend/artifacts/evaluation/runs/`.

## Profiles

- **Offline** is deterministic and network-free. It uses provider-neutral fakes while exercising
  routing, structured contracts, SQL validation, retrieval traversal, graph bounds, budgets,
  forecast math, privacy, reporting, and regression logic.
- **Integration** uses the real local synthetic PostgreSQL query boundary. NLP-to-SQL candidates
  and trusted references execute through the same read-only `QueryExecutor`; a monthly claim-volume
  case performs a historical holdout from seeded PostgreSQL data. Knowledge Catalog and Semantica
  build disposable evaluation-only LanceDB indexes with deterministic fake embeddings; these
  temporary fixtures never rebuild or modify the user's managed indexes. Model decisions remain
  deterministic fakes.
- **Live** uses the configured `LLMClient` without fallback. It is optional, consumes provider quota,
  and fails clearly when credentials are missing. Provider/model metadata, latency, and available
  token usage are reported without pricing estimates. Live retrieval requires existing managed
  Knowledge Catalog and Semantica indexes compatible with the configured embedding provider/model;
  the evaluator fails with rebuild guidance instead of silently rebuilding them.

```bash
cd backend
python -m app.evaluation.run --profile offline
python -m app.evaluation.run --profile integration
LLM_PROVIDER=gemini EMBEDDING_PROVIDER=gemini python -m app.evaluation.run --profile live
```

## What is measured

Routing reports accuracy and a machine-readable confusion matrix. NLP-to-SQL is scored primarily
by normalized result equivalence, not SQL string equality: candidate SQL is generated and
validated, candidate and trusted reference SQL stay separate, and both use the read-only executor
in integration/live runs. Normalization handles columns, row order, dates, nulls, numeric types,
and declared tolerances.

SQL safety only submits adversarial statements to the existing guard; destructive fixtures are
never executed. Data Discovery, Knowledge Catalog, Data Quality, and Semantica use hit/recall/MRR,
citation validity, and graph-distance measures. Advanced reasoning and multi-hop cases check only
observable plans, approved tools, dependencies, results, privacy, and budgets—never hidden
reasoning. Forecasting uses leakage-free holdouts with MAE, RMSE, sMAPE, a naive comparison, exact
horizons, future dates, ordered intervals, and nonnegative lower bounds.

Known-value privacy leak detection inspects only synthetic values supplied by each fixture. Hard
gates require zero unsafe executions, privacy leaks, invalid citations, unapproved tools, budget
violations, and graph-hop violations. Reports exclude secrets, mappings, resolved sensitive SQL,
SDK objects, and chain-of-thought.

## Baselines and artifacts

```bash
python -m app.evaluation.run --profile offline \
  --compare-baseline evals/baselines/offline-v1.json
python -m app.evaluation.run --profile offline \
  --write-baseline evals/baselines/offline-v1.json
```

An existing baseline is protected unless `--overwrite-baseline` is explicitly supplied. Quality
policies live in `backend/evals/config.yaml`; latency is visible but is not a default regression
gate. Generated runs are ignored by Git. Reviewed baselines and case YAML remain version-controlled.

Phase 20 never ingests production logs or user chats and does not provide a UI, online evaluator,
automatic prompt optimizer, model switcher, or mandatory LLM-as-judge.
