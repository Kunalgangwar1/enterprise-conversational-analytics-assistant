# ADR-015a: Multi-provider AI adapters

## Status

Accepted for Phase 15.

## Context

The source architecture used Azure OpenAI, while the clean-room reconstruction is moving toward AWS
deployment and the developer currently has Gemini API access. Application workflows already depend
on provider-neutral language-model and embedding contracts.

## Decision

Retain `LLMClient` and `EmbeddingClient` as the only business-layer AI interfaces. Keep the Azure
OpenAI adapters, add Gemini adapters using the official `google-genai` SDK, select providers only
through configuration, and make Gemini the development default. Amazon Bedrock remains a future
AWS-native adapter option and is not implemented in this phase.

## Alternatives considered

- Delete Azure: rejected because it removes a working optional integration and source fidelity.
- Hard-code Gemini in agents: rejected because it couples business workflows to one provider.
- Comment or uncomment provider code: rejected because deployment selection belongs in config.
- Require direct OpenAI API access now: rejected because it is not needed for this phase.
- Implement Bedrock before AWS deployment: rejected as premature and unnecessary.

## Consequences

- Existing agents switch providers without rewrites.
- Provider behavior can be tested and compared behind stable contracts.
- Each adapter requires focused normalization and error tests.
- Vector indexes must be rebuilt when provider, model, or dimensions change.
