# ADR-015: Separate specialist retrieval modes

## Status

Accepted for Phase 15.

## Context

Dataset lookup, data-quality guidance, and semantically connected catalog exploration are different
tasks. Treating them as one generic RAG path would add model cost to deterministic lookup, blur the
boundary between guidance and live measurements, and make graph expansion harder to reason about.

## Decision

- Data Discovery uses deterministic structured metadata search over seven registered datasets.
- Data Quality uses a dedicated synthetic guidance corpus, deterministic retrieval, grounded answer
  generation, and citation validation. It performs no live database profiling.
- Semantica uses LanceDB hybrid seed retrieval followed by deterministic adjacency expansion through
  at most two hops, then grounded citation-validated generation.

Each specialist receives privacy-safe text and remains separate from the routing-only supervisor.

## Consequences

- Specific metadata lookup remains fast, deterministic, and model-free.
- Data Quality answers cannot be confused with calculated production metrics.
- Semantica gains bounded relationship context without model-generated graph edges.
- Each specialist has an explicit API and independent tests and settings.
- Full conversational orchestration remains future work.
