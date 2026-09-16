# ADR-017: LLM-planned, deterministic aggregate forecasting

## Status

Accepted for Phase 17.

## Context

The source architecture includes forecasting under SQL/Data Intelligence. Forecast numbers must
be reproducible, testable, privacy-bounded, and unable to change when a language-model provider or
wording changes. The reconstruction already owns metadata-grounded SQL generation, validation,
privacy-token restoration, bounded query execution, and protected result previews.

## Decision

Use `LLMClient` only to produce a strict `ForecastPlan` and a final explanation. Reuse the standard
NLP-to-SQL and query-execution path for historical aggregates. Validate one regular temporal
series, then compute candidates, holdout metrics, selection, refit, future calendar periods, and
approximate intervals entirely in dependency-free Python. Treat the typed numerical result as
immutable at the explanation boundary.

Support only aggregate operational forecasting at day, week, or month frequency. Reject
individual clinical-outcome prediction before planning. Keep the capability internal, feature
gated, and reachable from the existing Data Intelligence route; add no public endpoint or
top-level mode.

## Consequences

- Forecasts remain deterministic and work with provider fakes in normal tests.
- Existing SQL safety, metadata grounding, token resolution, credentials, and row/time limits are
  not duplicated or bypassed.
- Simple models are understandable but do not provide causal inference or calibrated prediction
  intervals.
- Irregular or insufficient histories fail explicitly; Phase 17 does not impute data.
- More advanced statistical models, backtesting strategies, and public orchestration require a
  later explicit phase and architectural decision.
