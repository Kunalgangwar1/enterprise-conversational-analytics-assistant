# Advanced reasoning

Phase 16 implements the source architecture's optional generic reasoning promotion model without
changing the normal specialist path. `ReasoningPromotionPolicy` is deterministic: it returns
`ADVANCED` only when the single-intent flag is enabled, confidence meets the configured threshold,
the route is eligible and enabled, and an implementation for the corresponding application tool
is actually available. Otherwise it returns `STANDARD`; deciding promotion never calls an LLM.

## Bounded workflow

The provider-neutral `AdvancedReasoningPlanner` compiles this LangGraph:

```text
START -> decompose -> plan_tools -> execute -> reflect
                                             | sufficient
                                             v
                                          synthesize -> END
                                             ^
                                             | needs_more (at most once)
                                      plan_tools -> execute -> reflect
```

Decomposition, planning, reflection, and synthesis use structured Pydantic responses through
`LLMClient`. State contains only the privacy-safe question, route, concise structured tasks and
plans, normalized tool results, counters, warnings, and final synthesis. It never stores the raw
question, privacy mappings, credentials, SDK responses, or chain-of-thought. One additional
planning/reflection cycle is the hard application limit; LangGraph's recursion limit is not the
budget mechanism.

## Explicit tools

`AdvancedToolRegistry` exposes only injected application adapters for implemented capabilities:

- standard validated SQL analytics;
- aggregate operational forecasting;
- Knowledge Catalog;
- deterministic Data Discovery;
- Data Quality guidance;
- Semantica.

Availability also respects `AgentRegistry` and existing tool rollout flags. Forecasting is exposed
only when its Phase 17 adapter is injected and both controls enable it. Group Access remains
unimplemented. There are no shell, Python,
filesystem, arbitrary HTTP, raw-SQL, database-DDL, or AWS tools. Model-produced names,
dependencies, and instructions are validated before sequential execution; SQL/code/URL-shaped
instructions fail closed. Tool outputs are normalized without SDK objects, credentials, resolved
SQL, privacy mappings, or embedding vectors. Synthesis may cite only provenance returned by
successful tools.

The default `DEEP_AGENT_SINGLE_INTENT_ENABLED=false` keeps ordinary requests on the cheaper
standard specialist path. Phase 16 provides internal components only; full `POST /chat`
orchestration remains a later phase. All model calls are provider-neutral, normal tests use
`FakeLLMClient`, and no AWS resources or credentials are required.
