# ADR-021: Provider-neutral authentication, authorization, and RBAC

## Status

Accepted.

## Context

The application had feature/tool controls but no authenticated user identity or deterministic
authorization boundary. Production deployment requires server-side access control while local
learning workflows must remain usable without AWS or another identity provider.

## Decision

- Do not build or store username/password credentials.
- Normalize development or OIDC identities into immutable `AuthPrincipal` values.
- Restrict deterministic development authentication to local/development/test environments.
- Verify OIDC bearer JWT signatures and registered claims with PyJWT and cached issuer JWKS.
- Map the small viewer/analyst/admin role set to explicit permissions; unknown roles grant nothing.
- Treat configured external group mapping as the only way groups can add application roles.
- Enforce permissions in FastAPI routes, after chat routing, and in advanced tool selection and
  execution.
- Bind session persistence to authenticated subject plus browser cookie plus tab ID.
- Implement Group Access as deterministic current-principal introspection.
- Keep Cognito configuration behind the authentication backend for a future deployment phase.

## Rejected alternatives

- A custom password/user database
- Frontend-only authorization
- Treating feature flags or agent availability as permissions
- Asking an LLM to make authorization decisions
- Hard-coding Cognito throughout application services
- Accepting arbitrary development identity headers
- Making admin an unconditional bypass

## Consequences

Local development remains credential-free and deterministic. Application authorization is
identity-provider neutral, and future Cognito adoption configures issuer/JWKS/claims rather than
rewriting business workflows. Every privileged capability must declare a permission. Frontend
filtering improves UX but does not replace backend enforcement. Real hosted-login and browser token
lifecycle work remains deferred; no AWS account or resource is required by this decision.
