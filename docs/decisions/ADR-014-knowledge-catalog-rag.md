# ADR-014: Hierarchical-first Knowledge Catalog retrieval

## Status

Accepted for Phase 14.

## Context

Enterprise catalog questions need grounded answers across structured dataset descriptions,
policies, and lineage documents. Exact field names and paraphrased business questions require
different retrieval strengths, while sending the entire catalog to a model would be expensive and
poorly bounded.

## Decision

Use explicit hierarchical Markdown traversal as primary retrieval and local LanceDB hybrid vector
plus BM25 retrieval as fallback. LanceDB's Reciprocal Rank Fusion combines the two rankings. Both
paths return a common evidence model, and answer generation is bounded, treats retrieved text as
untrusted data, and rejects citations that are not part of the supplied evidence.

Azure OpenAI embeddings sit behind a provider-neutral lazy client. The catalog hierarchy remains
the version-controlled source; LanceDB and its safe manifest are generated local artifacts.

## Alternatives considered

- Entire catalog in one prompt: rejected because context is unbounded and unrelated content dilutes
  grounding.
- Vector-only retrieval: rejected because it discards the catalog's explicit hierarchy.
- Lexical-only retrieval: rejected because paraphrases may not share exact terms.
- FAISS plus a separate BM25 implementation: rejected because it duplicates storage and fusion
  concerns that current LanceDB supports.
- Immediate graph retrieval: deferred to Phase 15 to preserve incremental scope.
- LangChain RAG abstraction: rejected because the project already has small provider-neutral seams
  and does not need another framework.

## Consequences

- Hierarchical decisions are bounded and interpretable.
- Exact terms benefit from BM25 while paraphrases benefit from vectors.
- Hybrid fallback makes retrieval more robust when hierarchy confidence is insufficient.
- LanceDB adds a runtime dependency and generated local artifact.
- Live vector indexing and querying require a configured embedding deployment.
- Graph enrichment and two-hop expansion remain outside Phase 14.
