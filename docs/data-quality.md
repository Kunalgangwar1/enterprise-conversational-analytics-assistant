# Data Quality guidance

Phase 15 Data Quality provides grounded guidance, not live profiling. Original synthetic Markdown
under `backend/data/data_quality` covers completeness, freshness, validity, uniqueness,
consistency, seven dataset-specific rule pages, and generic remediation.

The loader validates required metadata, unique IDs, and safe source paths. Deterministic keyword
retrieval is bounded by `DATA_QUALITY_TOP_K` and uses no vector index. The agent builds a bounded,
provenance-labelled context, treats retrieved text as untrusted data, invokes only `LLMClient`, and
rejects citations not present in supplied evidence. No evidence returns a deterministic response
without calling a model.

The agent never queries PostgreSQL or `QueryExecutor` and must not claim measured null rates,
freshness percentages, duplicate counts, or quality scores. The request-scoped
`POST /api/data-quality/query` route applies privacy processing before the agent and current-token
unmasking afterward.
