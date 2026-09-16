# Security hardening and healthcare-data protection

Phase 23 adds clean-room production hardening around the reconstructed architecture. It does not
claim that every control existed in the source system, and it does not claim formal HIPAA or other
regulatory compliance. Compliance requires organizational, contractual, operational, and technical
assessment beyond this repository.

## Trust boundaries

The application treats browser/network input, user text, retrieved documents, metadata descriptions,
LLM output, and tool-derived content as untrusted. Security decisions remain in deterministic
application code:

- Phase 21 authentication, permissions, and execution-time RBAC are authoritative.
- Phase 9 privacy processing runs before external model calls.
- Phase 12 and Phase 4 validate SQL and execute it through bounded read-only database controls.
- Phase 13 executes only server-owned `SessionState.last_generated_sql`.
- Phase 16 restricts tools by typed registry, permissions, schemas, and budgets.
- Phase 22 protects subject-owned shared state with hashed keys and atomic updates.

Prompt text is defense in depth, not an authorization boundary.

## Production fail-closed policy

`APP_ENV=production` or `prod` rejects development authentication, insecure session cookies,
credentialed wildcard CORS, empty/wildcard trusted hosts, enabled API documentation, and disabled
rate limiting. OIDC remains provider-neutral and AWS is not required.

A production-oriented baseline is:

```dotenv
APP_ENV=production
AUTH_MODE=oidc
SESSION_COOKIE_SECURE=true
CORS_ALLOWED_ORIGINS=["https://analytics.example.invalid"]
CORS_ALLOW_CREDENTIALS=true
ALLOWED_HOSTS=["analytics.example.invalid"]
API_DOCS_ENABLED=false
RATE_LIMIT_ENABLED=true
RATE_LIMIT_BACKEND=redis
RATE_LIMIT_REDIS_URL=redis://:secret-from-a-secret-store@redis.internal:6379/1
SECURITY_HEADERS_ENABLED=true
HSTS_ENABLED=true
```

Enable HSTS only when HTTPS is guaranteed by the deployment edge. TLS termination, proxy trust,
ALB behavior, WAF, and the production frontend CSP remain deployment work for later phases.

## Browser and HTTP controls

CORS uses an exact configured origin allowlist, credentials only for current browser/session
behavior, methods `GET`, `POST`, and `OPTIONS`, and the current `Accept`, `Authorization`,
`Content-Type`, and `X-Tab-Id` headers. CORS does not replace authentication or RBAC.

Trusted-host middleware rejects unconfigured Host headers. Local defaults are `localhost`,
`127.0.0.1`, and `testserver`; production requires explicit values.

API responses receive `nosniff`, `Referrer-Policy: no-referrer`, `X-Frame-Options: DENY`, a restrictive
Permissions Policy, and `Cache-Control: no-store`. Pure API responses also receive a restrictive CSP.
Development documentation routes are excluded from that CSP because Swagger/ReDoc require browser
assets; production documentation is disabled. `X-XSS-Protection` is deliberately not used.

The browser session cookie is opaque state coordination, not authentication proof. It remains
`HttpOnly`, `SameSite=Lax`, scoped to `/`, has no Domain attribute, and uses the existing Max-Age.
Production requires `Secure=true`.

## CSRF threat model

Production-style identity uses an explicit `Authorization: Bearer` token. The opaque session cookie
does not authenticate a user, so a separate CSRF token subsystem is not added in this phase. Exact
CORS and RBAC remain enforced. If authentication moves to an automatically sent browser cookie,
explicit CSRF protection becomes mandatory before deployment.

## Request and abuse bounds

`REQUEST_MAX_BODY_BYTES` defaults to 64 KiB. The ASGI middleware reads at most that bound and checks
actual received bytes, so missing or misleading Content-Length and streamed/chunked bodies cannot
bypass it. Oversized requests return the existing safe envelope with HTTP 413. Health GETs do not
consume or buffer a body.

Chat messages and direct specialist questions are limited to 4,000 characters; custom context is
limited to 8,000. Unsupported C0/C1 control characters are rejected, while ordinary tabs and
newlines remain usable. Input is rejected rather than silently truncated, and healthcare/business
keywords are not blacklisted.

Expensive authenticated operations (`/chat`, `/chat/execute-sql`, and direct specialist query
routes) use subject-scoped fixed windows. Keys contain a SHA-256 digest rather than raw subjects or
emails. Local development uses a deterministic process-local backend. Shared deployments can use
the existing redis-py dependency and an atomic Lua fixed-window increment/expiry operation. Limits
return HTTP 429 plus `Retry-After`. Redis limiter outages fail safely with a sanitized 503; there is
no implicit memory fallback. `/api/health` is public, minimal, and unthrottled.

## GenAI and retrieval safety

System/application instructions are role-separated from delimited untrusted user input, metadata,
retrieved evidence, and reasoning/tool context. Prompts explicitly state that embedded instructions
cannot change permissions, tools, SQL safety, privacy, or budgets and must not disclose system
instructions or credentials. There is no prompt-injection keyword blacklist.

Indirect instructions in Knowledge Catalog, Data Quality, and Semantica evidence remain evidence,
not system messages. Citation membership validation still rejects invented sources. Advanced
Reasoning continues to expose only permission-filtered typed application tools; it adds no shell,
`eval`, HTTP-fetch, filesystem, or arbitrary SQL capability.

Authentication subject metadata, email, groups, roles, permissions, and raw JWTs are not supplied to
models. The privacy boundary tokenizes supported synthetic business identifiers and redacts email,
phone, obvious bearer-token text, and explicit credential assignments. Raw prompts, token mappings,
Authorization headers, provider keys, database passwords, and Redis URLs must not be logged.

Model output is structured and validated where required. The React UI renders returned text through
normal escaped JSX; it does not use `dangerouslySetInnerHTML`, `eval`, `new Function`, or dynamic
script injection. The frontend stores only the non-secret tab identifier in session storage and does
not persist bearer or refresh tokens.

## SQL and error defense in depth

Multi-statement input, DML, DDL, COPY, transaction/control statements, comment bypasses, write CTEs,
locks, and unknown privacy tokens remain rejected before execution. The executor still applies a
read-only transaction, database reader role, timeout, and row bound. Clients cannot submit SQL to
`POST /chat/execute-sql`; only the validated pending SQL owned by the current subject/browser/tab is
used.

Controlled errors do not include tracebacks, filesystem paths, SQLAlchemy internals, connection
strings, Redis details, JWT validation internals, or provider credentials. The public health body is
only `{"status":"ok"}`. Database DSNs and secret values are excluded or masked in Settings text
representations; safe configuration summaries expose counts and booleans only.

## Dependencies and future deployment responsibilities

Phase 23 does not perform forced upgrades or `npm audit fix --force`. Dependency audit findings are
reported for controlled remediation and can be automated in Phase 25. Phase 26 must finalize TLS,
edge/frontend CSP, reverse-proxy and forwarded-header trust, and deployed identity/network controls.
Later phases own centralized secret storage, operational logging/redaction, WAF, observability,
resilience, and load/abuse testing.
