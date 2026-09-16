# Semantica

Semantica is a separate specialist that combines LanceDB hybrid seed retrieval with deterministic
adjacency expansion. It reuses suitable synthetic Knowledge Catalog leaf documents and never
indexes database rows.

`python -m app.semantica.index` applies dedicated `SEMANTICA_CHUNK_SIZE_CHARS=900` and
`SEMANTICA_CHUNK_OVERLAP_CHARS=120` settings, embeds through the selected `EmbeddingClient`, writes
the separate `semantica_chunks` table, builds FTS, and persists a safe manifest plus adjacency JSON.
Stable chunk IDs are used. Sequential chunks, structurally related catalog siblings, and explicit
claims/encounter lineage pairs create bidirectional edges without NetworkX or model-generated
relationships.

Retrieval uses LanceDB vector and BM25 search with Reciprocal Rank Fusion for up to
`SEMANTICA_SEED_TOP_K` seeds. A visited set expands distance 1 then distance 2, never distance 3;
`SEMANTICA_MAX_EVIDENCE` bounds and deduplicates results. Seeds precede hop-one and hop-two evidence,
with seed rank and stable IDs determining ties.

The selected embedding provider/model/dimensions must match the index manifest. Switching between
Gemini and Azure requires an explicit managed-index rebuild. The grounded agent depends only on
`LLMClient`, treats retrieved content as untrusted evidence, and validates every citation. The
`POST /api/semantica/query` privacy boundary returns only answer, retrieval method, and safe
citation metadata—never vectors or adjacency internals.
