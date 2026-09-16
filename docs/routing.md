# Supervisor and intent routing

Phase 10 introduces internal route selection and stops at a typed `SupervisorDecision`. It does not
execute a specialist, answer the user, or add a routing or chat HTTP endpoint.

## Top-level modes and internal routes

The existing user-selectable top-level modes remain:

```text
auto, sql, group_access, data_discovery, knowledge_catalog, semantica, data_quality
```

The supervisor's internal routes are:

```text
group_access, sql, forecasting, chat, help, data_discovery,
knowledge_catalog, semantica, data_quality
```

`auto` invokes routing and is not a specialist route. `forecasting`, `chat`, and `help` are internal
only; the Phase 6 `ChatModeRegistry` is unchanged. Historical source aliases are not reproduced.

## Privacy boundary

The intended composition is:

```text
raw user text
  -> PrivacyProcessor
  -> safe_text
  -> SupervisorMultiAgent
  -> SupervisorDecision
  -> future specialist
```

`IntentRouterAgent.classify()` and `SupervisorMultiAgent.route()` deliberately name their input
`safe_text`. They do not perform redaction themselves. A future `ChatService` will compose the
privacy processor before the supervisor. Routing code does not log request text or privacy
mappings.

## Explicit-mode policy

Every non-`auto` top-level selection is a hard constraint and bypasses general LLM classification:

| Selected mode | Internal route |
|---|---|
| `group_access` | `group_access` |
| `data_discovery` | `data_discovery` |
| `knowledge_catalog` | `knowledge_catalog` |
| `semantica` | `semantica` |
| `data_quality` | `data_quality` |
| `sql` | `sql`, or `forecasting` for a strong analytical forecast request |

An explicitly selected disabled route raises `RoutingUnavailableError`; it does not silently change
to another capability. Forecasting is a SQL/Data Intelligence sub-route: if its narrow heuristic
matches but forecasting is disabled, the supervisor stays on `sql` when SQL is enabled.

## Auto-mode policy

Auto mode applies these steps:

1. Evaluate a small ordered set of high-confidence heuristics.
2. Return an enabled heuristic route without calling an LLM.
3. Otherwise request a structured `LLMIntentDecision` from `IntentRouterAgent`.
4. Accept an enabled result at or above `INTENT_ROUTER_MIN_CONFIDENCE`, which defaults to `0.60`.
5. Use `knowledge_catalog` when confidence is below the threshold or the predicted route is
   disabled.
6. Raise `RoutingUnavailableError` if the knowledge-catalog fallback is also disabled.

Low classifier confidence means uncertainty and uses the documented fallback. LLM authentication,
timeout, rate-limit, and provider failures instead become chained routing errors; they are not
presented as successful fallback decisions.

## Deterministic heuristics

The rules cover only narrow cases and otherwise return no decision. Access and data-quality rules
run before general classification. Semantica requires the literal product name; a generic semantic
or ontology question does not activate it. Data discovery requires a specific dataset, table,
schema, or source-location request. Forecasting requires future-looking language and analytical
context. Help and greeting detection are intentionally small.

Representative outcomes:

| Mode | Safe request | Result |
|---|---|---|
| `auto` | “How can I request access to the claims dataset?” | `group_access` heuristic |
| `auto` | “Why are there null values in this dataset?” | `data_quality` heuristic |
| `auto` | “Find the dataset containing appointment information.” | `data_discovery` heuristic |
| `auto` | “Use Semantica to search for this.” | `semantica` heuristic |
| `sql` | “Forecast paid claims next quarter.” | `forecasting` sub-route |
| `sql` | “Show claims from 2026.” | forced `sql` route |
| `auto` | “Show total paid claims by specialty.” | structured LLM classification, commonly `sql` |
| `auto` | “Explain our lineage policy.” | structured classifier or low-confidence `knowledge_catalog` fallback |

## Structured intent classifier

`IntentRouterAgent` depends only on the provider-neutral `LLMClient`. Its fixed system instruction
describes the nine internal routes and asks for the Pydantic `LLMIntentDecision` schema containing
only `intent` and bounded `confidence`. User content is placed in a separate user-role message and
is never appended to the system instruction. Structured validation limits the output to known
routes, although role separation alone is not a complete prompt-injection defense.

## Agent registry

`backend/config/agents_registry.yaml` represents every internal route with an `enabled` boolean.
The loader uses `yaml.safe_load`, strict Pydantic validation, and an immutable `AgentRegistry`
interface with `is_enabled`, `require_enabled`, and deterministically ordered `list_enabled`.
Missing, malformed, incomplete, or unknown configuration fails clearly when routing is constructed.

Registry eligibility is separate from Phase 2 UI/tool flags. `enabled` means only that the route may
be selected; it does not claim that the full specialist is implemented or make the capability
visible in the UI.

## Deferred execution

The supervisor does not call `MetadataRegistry`, `QueryExecutor`, retrieval systems, SQL generation,
or specialist services. Phase 16 adds a separate deterministic `ReasoningPromotionPolicy` and
bounded `AdvancedReasoningPlanner`, but deliberately does not turn the supervisor into an executor.
No supervisor-to-agent chat wiring or complete chat endpoint exists yet. See
[`advanced-reasoning.md`](advanced-reasoning.md).
