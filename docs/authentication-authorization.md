# Authentication and authorization

Phase 21 adds an identity-provider-neutral security boundary. Authentication establishes who made
a request; authorization determines whether that authenticated principal may use a capability.
Feature flags, agent availability, and permissions remain independent controls and all applicable
controls must allow execution.

## Request boundary

```text
HTTP request
    -> AuthenticationBackend
    -> AuthPrincipal
    -> AuthorizationService
    -> endpoint/route/tool permission
    -> application capability
```

`AuthPrincipal` contains only normalized subject, optional email/display name, application roles,
external groups, scopes, effective permissions, and authentication method. Raw JWTs, signatures,
refresh tokens, passwords, and provider claim dictionaries never enter application services or LLM
prompts.

## Authentication modes

`AUTH_MODE=development` returns one deterministic configured identity without a browser token or
network request. It is permitted only when `APP_ENV` is local, development, dev, or test; settings
validation rejects it in production. Browser-supplied `X-User`, `X-Role`, and `X-Admin` headers are
ignored.

`AUTH_MODE=oidc` requires `AUTH_OIDC_ISSUER` and `AUTH_OIDC_JWKS_URL`. PyJWT selects cached issuer
JWKS keys and cryptographically verifies the signature, explicit algorithm allowlist, expiration,
optional not-before, issuer, configured audience, and required subject. Optional expected token use
is enforced. Claim names are configurable, and external groups become roles only through the
explicit JSON `AUTH_GROUP_ROLE_MAPPING`. Unknown roles and unmapped groups grant nothing.

This supports a future Cognito issuer/JWKS configuration without embedding Cognito or AWS SDK logic
in chat, dashboard, SQL, retrieval, or forecasting code. Phase 21 creates no AWS resources and no
redirect/login UI.

## Role and permission policy

Permissions—not role-name checks—are the authorization primitive. Admin is explicit permission
composition, not a bypass.

| Capability | Viewer | Analyst | Admin |
|---|:---:|:---:|:---:|
| Chat | yes | yes | yes |
| Dashboard | yes | yes | yes |
| Data Discovery | yes | yes | yes |
| Knowledge Catalog | yes | yes | yes |
| Data Quality | yes | yes | yes |
| Semantica | yes | yes | yes |
| SQL Generate | no | yes | yes |
| SQL Execute | no | yes | yes |
| Advanced SQL | no | yes | yes |
| Forecasting | no | yes | yes |
| Group Access Self | yes | yes | yes |
| Admin Authorization | no | no | yes |

Stable permission identifiers are `chat.use`, `dashboard.read`, `data_discovery.read`,
`knowledge_catalog.read`, `data_quality.read`, `semantica.read`, `sql.generate`, `sql.execute`,
`sql.advanced`, `forecast.run`, `group_access.read_self`, and `admin.authorization.read`.

## Enforcement

`GET /api/health` remains public. Application endpoints authenticate through reusable FastAPI
security dependencies. Missing/invalid authentication returns the safe `authentication_required`
401 envelope; a valid principal missing permission returns `permission_denied` with 403.

Chat authorization also occurs after Supervisor routing and before specialist execution, so Auto
mode cannot turn `chat.use` into SQL or forecast access. Standard SQL, advanced multi-hop SQL, and
forecasting require their separate permissions. Generic advanced reasoning receives a
request-scoped tool registry filtered by effective permissions, and the registry checks again at
execution. Backend checks are authoritative; frontend filtering only improves usability.

## Group Access

The `group_access` route is deterministic and calls no LLM or database. It reports the current
principal's display name, roles, external groups, effective permissions, and safe capability
summaries. `group_access.read_self` cannot search a user directory or inspect another email. The
response contains no token or raw provider metadata.

## Session ownership

Authenticated session identity is:

```text
subject + browser session cookie + X-Tab-Id
```

All three values feed the SHA-256 persistence key, and `owner_subject` is validated on load. A
second subject using the same browser cookie and tab receives a separate empty session and cannot
inherit history, accepted SQL, privacy token mappings, or follow-ups. Pre-Phase-21 unowned local
files retain their legacy key but authenticated requests never resolve that key, which safely resets
legacy demo state rather than exposing it across identities. Same-user tab isolation is unchanged.

## Frontend boundary

The React `AuthProvider` calls `GET /api/auth/me` and represents loading, authenticated,
unauthenticated, and error states. Development mode displays the configured identity automatically.
Navigation, modes, and SQL strategies are filtered using effective permissions. No access or
refresh token is written to localStorage/sessionStorage; only the existing opaque tab identifier is
stored. A future phase may attach an actual Cognito browser login/token lifecycle to this boundary.
