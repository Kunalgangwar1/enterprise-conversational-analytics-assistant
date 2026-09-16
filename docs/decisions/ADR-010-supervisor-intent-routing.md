# ADR-010: Separate supervisor routing from specialist execution

- Status: Accepted
- Date: 2026-09-14

## Context

The application represents multiple specialized enterprise capabilities and must choose the
appropriate handler without coupling route selection to the handler's execution. User-selected
modes should remain authoritative, high-confidence operational requests should not always incur an
LLM call, and ambiguous requests need a constrained classification contract.

## Decision

Introduce `SupervisorMultiAgent` with a provider-neutral `IntentRouterAgent`. Use explicit user
modes as hard routing constraints, a small set of deterministic rules for high-confidence intents,
structured LLM classification for ambiguous auto-mode requests, and `knowledge_catalog` as the
low-confidence fallback. Use a typed `agents_registry.yaml` to control internal route eligibility
independently from product feature flags.

The supervisor accepts privacy-processed text and returns only `SupervisorDecision`. It does not
execute specialists. A disabled explicit route fails; a disabled auto-mode selection can use the
enabled knowledge-catalog fallback. Provider failures remain errors rather than being treated as
classification uncertainty.

## Alternatives considered

- Use one large agent for every request
- Use LLM routing for every request
- Use regex-only routing
- Execute specialists directly inside the router
- Introduce a LangGraph supervisor immediately

## Consequences

- Deterministic rules reduce unnecessary LLM calls.
- Explicit user mode selection is respected.
- Structured decisions constrain routes and confidence values.
- Ambiguous routing remains flexible through the provider-neutral LLM boundary.
- LLM availability still matters for ambiguous auto-mode requests.
- Route eligibility can be changed without changing UI/tool flags.
- Specialist execution and advanced-reasoning promotion remain later concerns.
