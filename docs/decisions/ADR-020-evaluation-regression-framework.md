# ADR-020: Evaluation and regression framework

## Status

Accepted

## Context

The application now has LLM-driven, retrieval-driven, deterministic analytical, safety, and
privacy components. A prompt, provider, model, corpus, or code change can improve one route while
silently breaking another. Unit tests alone do not measure cross-component analytical quality.

## Decision

We will version synthetic golden cases and run them through separate offline, integration, and live
profiles. NLP-to-SQL is evaluated primarily through safe result equivalence; retrieval through
objective evidence and citation metrics; forecasting through holdout numerical metrics; and
privacy/safety through zero-tolerance invariants. Each run writes JSON and Markdown, supports
explicit baseline comparison, and exits nonzero for failed cases or gated regressions. Live
provider evaluation remains optional.

The harness is an application sidecar and never participates in production requests. It does not
evaluate production conversations or expose hidden model reasoning.

## Alternatives considered

- Unit tests alone do not measure model/retrieval behavior across boundaries.
- Exact generated-SQL matching rejects valid equivalent queries.
- UI-only manual testing is not reproducible or machine-readable.
- LLM-as-judge for every case adds cost, nondeterminism, and circular evaluation.
- Production-conversation evaluation introduces privacy and governance risks.
- External evaluation SaaS would obscure the mechanics this learning reconstruction is intended
  to own.

## Consequences

Regressions and provider/model changes become measurable, and Phase 25 can consume JSON as a CI
quality gate. Curated cases and reviewed baselines require maintenance. Live evaluation consumes
tokens and remains partially nondeterministic, while offline results do not claim live-model
quality.
