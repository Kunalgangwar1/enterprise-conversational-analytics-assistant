# ADR-016: Bounded advanced reasoning and multi-hop NLP-to-SQL

## Status

Accepted for Phase 16.

## Context

Some high-confidence requests need coordinated application tools or several dependent analytical
queries. Sending every request through a deep agent would increase latency, cost, and failure
surface, while letting a model execute arbitrary code or SQL would bypass established safety
boundaries.

## Decision

- Keep standard specialist routing as the default.
- Promote only through a deterministic feature/confidence/route/agent/tool policy.
- Implement a bounded LangGraph `AdvancedReasoningPlanner` with explicit application tools and at
  most one replan cycle.
- Keep the SQL-specific `MultiHopNLP2SQLAgent` separate from generic tool coordination.
- Reuse the standard validated NLP-to-SQL path for every hop; planners never generate SQL.
- Reuse the existing `QueryExecutor` through stricter per-hop row and timeout allowances, without a
  second database engine.
- Protect and bound intermediate results before any later LLM call.
- Use structured synthesis followed by deterministic Markdown rendering and delta grounding.

## Alternatives considered

- Route every request through a deep agent.
- Use one giant prompt or unlimited reflection loops.
- Let a planner generate or execute raw SQL.
- Allow unlimited SQL hops, rows, or time.
- Add a multi-hop-specific database connection.
- Nest multi-hop SQL inside the generic planner.
- Treat future forecasting as analytical multi-hop work.

## Consequences

Advanced reasoning is opt-in and ordinary requests remain cheaper. Dependent analytics can reuse
prior protected results while latency, rows, execution time, and loop count remain bounded. The
additional state and failure paths need Phase 20 evaluation to demonstrate a measurable quality
benefit. Phase 16 creates no public endpoint, AWS resource, or forecasting behavior.
