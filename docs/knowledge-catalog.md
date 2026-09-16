# Knowledge Catalog retrieval

Phase 14 implements the `knowledge_catalog` specialist over an original synthetic healthcare
catalog. It answers dataset, field, policy, and lineage questions without implementing the Phase
15 Semantica graph.

## Retrieval policy

```text
safe_question
    |
    v
explicit Markdown hierarchy -- sufficient leaf evidence --> grounded answer
    |
    `-- insufficient --> LanceDB vector + BM25 FTS -- RRF --> grounded answer
```

`HIERARCHICAL_RAG` and `VECTOR_RAG` are loaded by the existing functionality-flag subsystem and
are both enabled in the default local configuration. Hierarchical traversal is always attempted
first when enabled. It starts at the explicit root and gives the provider-neutral `LLMClient` only
each level's child ID, title, summary, and node type. Structured child selections and confidence
are validated, and depth and branch counts are bounded. Unknown IDs fail validation.

Meaningful leaf evidence at or above `KNOWLEDGE_HIERARCHY_MIN_CONFIDENCE` completes the primary
path without opening LanceDB or constructing an embedding client. Insufficient evidence uses the
hybrid fallback when enabled. If neither path supplies evidence, the agent returns a deterministic
no-evidence answer without asking an LLM to guess.

## Synthetic hierarchy

Source documents live in `backend/data/knowledge_catalog`. YAML front matter explicitly defines
node IDs, node types, summaries, children, and parents. The loader requires one root, unique IDs,
existing child references, consistent parent links, an acyclic root-connected hierarchy, non-empty
titles and summaries, and source files that resolve inside the configured catalog directory.

The concise leaf documents describe the seven Phase 3 synthetic tables plus generic access,
retention, sensitive-data, and lineage guidance. No real organization, patient, member, or
production data belongs in this corpus.

## Chunking, embeddings, and LanceDB

Leaf Markdown is split deterministically at headings and then at paragraph boundaries where
practical. `KNOWLEDGE_CHUNK_SIZE_CHARS` and `KNOWLEDGE_CHUNK_OVERLAP_CHARS` bound chunks. Stable IDs
derive from source identity and ordinal position; each chunk retains node, title, section, path,
type, domain, and text metadata.

`EmbeddingClient` separates indexing and retrieval from provider SDKs. Gemini is the active local
default and uses the official `google-genai` embedding API with `GEMINI_EMBEDDING_MODEL`; the Azure
OpenAI adapter remains available through `EMBEDDING_PROVIDER=azure_openai`. Client construction and
calls are lazy, so importing the app and starting FastAPI require no embedding credentials.
Provider failures are translated to embedding-specific exceptions, and text, vectors, keys, and
prompts are not logged.

The index manifest records embedding provider, model or deployment, and dimensions. Those values
are checked before retrieval. Vectors from different providers, models, or dimensions are not
interchangeable: a mismatch fails before search and instructs the operator to rebuild the managed
index with `python -m app.knowledge_catalog.index`.

Run the live index builder from `backend`:

```bash
python -m app.knowledge_catalog.index
```

It validates and chunks the corpus, embeds every chunk, replaces the local `knowledge_chunks`
table, creates a LanceDB full-text index, and writes a safe manifest. Generated files live beneath
`backend/artifacts/knowledge_catalog` and are ignored by Git. The manifest contains counts,
provider/model identifiers, dimensions, corpus hash, and build time—never keys, vectors, or full
document rows.

Hybrid retrieval sends an explicit custom query vector and text query to LanceDB. LanceDB performs
vector similarity and BM25 full-text search, then its native `RRFReranker` applies Reciprocal Rank
Fusion. This lets exact terms such as `allowed_amount` benefit from lexical matching while
paraphrases benefit from embeddings. The current architecture uses LanceDB; references to FAISS in
historical source notes describe an older design and are not implemented here.

## Grounding and privacy

Both retrieval paths return the same `KnowledgeEvidence` model. The context builder includes only
bounded, clearly delimited evidence with ID, title, section, source path, and text. Retrieved text
is treated as untrusted data. The answer system prompt says document instructions cannot override
system rules, answers must use supplied evidence, insufficient evidence must be acknowledged, and
citations must use supplied evidence IDs.

The `KnowledgeCatalogAgent` validates every structured citation before returning it. An invented
citation fails rather than being silently displayed. This prompt and validation boundary reduces
risk from indirect prompt injection but is not a complete prompt-injection defense.

The agent accepts only a `safe_question`; it does not invoke privacy processing itself. The
specialist API owns the full boundary:

```text
raw question -> PrivacyProcessor -> KnowledgeCatalogAgent -> ResponseUnmasker -> response
```

Only current request tokens can be restored. Privacy mappings, vectors, prompts, embeddings, and
provider responses are absent from the API contract and logs.

## Specialist API and live smoke

`POST /api/knowledge-catalog/query` accepts `{"question": "..."}` and returns the grounded answer,
retrieval method, and safe citation metadata. It is request-scoped and does not require sessions or
conversational follow-up state. Full `POST /chat` orchestration is intentionally outside Phase 14.

With the selected chat and embedding providers configured and the index built, an optional live
check can be run from `backend`:

```bash
python -m app.knowledge_catalog.smoke "What does allowed amount mean for a claim?"
```

An embedding-only check is available as `python -m app.knowledge_catalog.embedding_smoke`; it prints
provider, model, and vector dimensions, never values. Missing live configuration is reported
explicitly. Semantica graph traversal is implemented separately in Phase 15.
