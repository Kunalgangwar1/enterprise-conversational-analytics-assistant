# ADR-008: Isolate LLM providers behind a typed application contract

- Status: Accepted
- Date: 2026-09-14

## Context

Multiple future agents and workflows will require language-model access. The documented source
architecture uses Azure OpenAI and optionally another provider gateway. Calling a provider SDK
directly throughout future workflows would duplicate request translation, configuration, error
handling, and testing concerns.

## Decision

Introduce a provider-neutral `LLMClient` with typed request and response models. Implement Azure
OpenAI as the first provider using the official OpenAI Python SDK Responses API for plain text and
SDK-native Pydantic structured parsing. Construct the provider lazily from environment settings and
centralize timeout, transport retry, usage mapping, endpoint normalization, and exception
translation.

## Alternatives considered

- Use the OpenAI/Azure SDK directly inside every future agent
- Introduce LangChain immediately
- Implement multiple real providers immediately
- Expose a generic raw LLM HTTP endpoint

## Consequences

Future workflows remain provider-independent, provider configuration and failures have one
boundary, and deterministic fake clients support network-free tests. Azure OpenAI is the only real
provider currently implemented. Another adapter can be added later without changing workflow
contracts, but no Anthropic adapter or fallback exists yet.
