# Synthetic evaluation datasets

Phase 20 keeps curated, client-independent golden cases in `cases/`. Every file declares a
`dataset_version`, every case has a stable descriptive ID, and IDs are unique across all suites.
The loader rejects unknown fields and duplicate IDs.

To add a case:

1. Choose the suite whose product boundary owns the behavior.
2. Add a stable ID such as `route-016` or `sql-claims-011`; never use a random UUID.
3. State objective expectations such as a route, evidence ID, result table, tool, bound, or numeric
   future. Do not exact-match generated prose.
4. For NLP-to-SQL, write a read-only PostgreSQL `reference_sql` against only the synthetic schema.
   It is evaluation-only and is never included in a model prompt. Include deterministic offline
   result fixtures and use aggregate outputs rather than member-identifying rows.
5. Increment the file's dataset version when its measured contract changes.

Run one suite or case from `backend/`:

```bash
python -m app.evaluation.run --profile offline --suite routing
python -m app.evaluation.run --profile offline --case-id route-001
```

All content must remain synthetic. Do not copy production conversations, logs, prompts, client
terms, PHI, credentials, or privacy mappings into these datasets.
