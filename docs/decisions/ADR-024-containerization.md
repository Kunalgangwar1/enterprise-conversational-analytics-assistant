# ADR-024: Containerized local integration stack

- Status: Accepted
- Date: 2026-09-17

## Context

The reconstruction needs reproducible application images and a local environment that exercises
the actual PostgreSQL and Redis boundaries without requiring host-installed runtimes or cloud
services. This environment must preserve the read-only query role and Phase 23 production security
policy while remaining convenient for local development.

Docker Compose is local integration infrastructure. It is not a decision about the final AWS
deployment topology, which remains Phase 26 work.

## Decision

Build independent multi-stage images for the FastAPI backend and React frontend. The backend uses
the locked Python dependency graph and runs Uvicorn as a dedicated non-root user. The frontend is
built with Node and served by unprivileged nginx, which also proxies the application's `/api` and
`/chat` paths for same-origin browser access.

Compose supplies PostgreSQL and Redis on its internal network with named persistent volumes.
PostgreSQL initialization creates a schema-owner application role and a separate SELECT-only query
role, including default SELECT grants for migration-created tables. Alembic runs as a one-shot
migration service; application replicas do not independently migrate. Synthetic seeding is an
explicit, guarded command rather than an automatic startup action.

Service ordering uses health checks and successful migration completion. Configuration and secrets
are injected at runtime from an ignored local environment file. Images contain no cloud or database
credentials. Local Compose uses development authentication and HTTP-compatible security settings;
the existing production validator remains unchanged.

## Consequences

Builds do not depend on the developer `.venv` or `node_modules`. PostgreSQL and Redis state survives
normal container recreation. A clean first startup applies migrations before serving traffic, and
generated SQL remains isolated to the reader role. The backend and frontend images can later be
evaluated independently for a production platform without treating this Compose topology as that
platform.

Changing PostgreSQL bootstrap identities after a volume has initialized requires an intentional
local data reset or manual administration. LLM-backed features still require runtime provider
configuration, but container startup and deterministic functionality do not.

## Alternatives considered

- One container for every process: rejected because it couples lifecycles and obscures readiness.
- Webpack's development server in the runtime image: rejected because it is not a production static
  server.
- Running the backend or frontend as root: rejected as unnecessary privilege.
- SQLite instead of PostgreSQL: rejected because it would bypass the implemented SQL dialect,
  migrations, and read-only role boundary.
- JSON sessions or process-local rate limits: rejected for this stack because real shared Redis
  behavior is a Phase 24 objective.
- Sleep-based startup ordering: rejected because elapsed time does not establish readiness.
- Secrets baked into image layers: rejected because layers are durable and distributable.
- Automatic seeding on every startup: rejected because the current seed intentionally refuses
  populated tables and startup must not destroy or duplicate data.
