# ADR-023: Explicit application and GenAI security boundaries

## Status

Accepted.

## Context

The reconstruction already had layered authentication, authorization, privacy, SQL validation,
bounded tools, and subject-owned sessions. Production use introduces additional browser/network,
resource-exhaustion, prompt-injection, indirect-retrieval, output-handling, and secret-disclosure
risks. These controls are clean-room production hardening around the reconstructed design.

## Decision

- Fail closed on clearly unsafe production authentication, cookie, CORS, host, documentation, and
  rate-limit configuration.
- Define exact CORS origins/headers/methods and trusted Host values.
- Add conservative API response headers and opt-in HSTS for HTTPS-guaranteed deployments.
- Bound actual streamed request bodies and user-controlled text without silent truncation.
- Rate-limit expensive authenticated operations by hashed subject using memory locally or atomic
  Redis fixed windows for shared deployments; return 429 with Retry-After and fail safe on outage.
- Treat user text, retrieved text, metadata descriptions, and content-derived tool output as
  untrusted data with explicit prompt roles and delimiters.
- Keep authorization, tool selection, budget enforcement, citations, structured output, privacy,
  and SQL validation outside the LLM.
- Keep secrets, raw JWT/auth metadata, and raw healthcare identifiers out of model context and safe
  errors by default.
- Render model text as escaped data, never executable HTML/JavaScript.
- Preserve server-owned SQL and the existing read-only database defense in depth.
- Make no formal HIPAA or regulatory-compliance claim.

## Rejected alternatives

- Wildcard credentialed CORS or arbitrary Host headers
- Frontend-only authorization or rate limiting
- Prompt-injection keyword blacklists
- Trusting retrieved RAG content as instructions
- Letting an LLM decide permissions or expand its tool registry
- Arbitrary client-submitted raw SQL execution
- Unbounded or Content-Length-only request limits
- Raw subjects/emails in shared limiter keys
- Logging full prompts, privacy mappings, tokens, or secrets
- Automatic limiter fallback that silently removes shared protection
- Forced dependency upgrades or `audit --force` during security hardening
- Claiming compliance without a formal organizational assessment

## Consequences

Unsafe production settings stop application construction. Browser requests and expensive operations
have explicit trust and resource boundaries. Model/retrieval instructions remain advisory defense in
depth while deterministic controls remain authoritative. Redis rate limiting adds a production
availability dependency and returns a controlled 503 when it cannot decide safely. Local workflows
remain network-free and use in-memory limiting. Deployment-specific TLS, proxy, WAF, secrets,
observability, and compliance work remains intentionally deferred.
