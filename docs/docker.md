# Local containerized stack

Phase 24 provides production-capable backend and frontend images plus a convenient local integration
stack. Docker Compose is not the final AWS topology; that decision belongs to Phase 26.

## Prerequisites and environment

Install Docker with the Compose plugin. No local Python, Node.js, PostgreSQL, Redis, cloud account,
or LLM credential is required to build and start the stack.

Create the ignored local Compose environment file and replace all placeholder passwords with
URL-safe, local-only values:

```bash
cp .env.docker.example .env.docker
```

`.env.docker` is ignored. The tracked example contains no real secret. Do not reuse its values in a
shared or deployed environment, and never add Gemini, Azure, AWS, JWT, or production database
credentials to an image or Dockerfile.

## Architecture and services

```text
postgres --healthy--> migrate --completed--> backend --healthy--> frontend
redis ----healthy---------------------------> backend
```

- `postgres` uses PostgreSQL 16 and the persistent `postgres_data` volume.
- `redis` uses Redis 7.4 with append-only persistence in `redis_data`.
- `migrate` runs `alembic upgrade head` once with the application/schema-owner role.
- `backend` runs Uvicorn as the non-root `eca` user on container port 8000.
- `frontend` builds React with Node 22, then serves static files and proxies API traffic through
  unprivileged nginx on container port 8080.
- `seed` is an explicit optional service and never runs during ordinary startup.

The browser calls the frontend origin. nginx forwards only `/api/*`, `/chat`, and `/chat/*` to
`backend:8000`; Docker-internal hostnames are never emitted into browser configuration. HashRouter
URLs such as `#/` and `#/dashboard` remain client-side routes.

## Build and start

Validate and build independently:

```bash
docker compose --env-file .env.docker config
docker compose --env-file .env.docker build backend
docker compose --env-file .env.docker build frontend
```

Start the complete unseeded stack:

```bash
docker compose --env-file .env.docker up -d --build --wait
```

Compose waits for PostgreSQL and Redis health, requires the migration service to complete, and then
starts the backend and frontend. No arbitrary sleep loop is used. Local Compose deliberately uses
`APP_ENV=development`, development authentication, HTTP-compatible cookies, disabled HSTS, and
Redis-backed sessions/rate limiting. It does not weaken the production settings validator.

Open `http://localhost:5173/#/` for chat or `http://localhost:5173/#/dashboard` for dashboards.
The backend is also exposed at `http://localhost:8000` for local API debugging. PostgreSQL and Redis
have no published host ports.

## Database roles, migrations, and synthetic seed

The first PostgreSQL volume initialization creates two non-superuser login roles:

- `eca_app` (or `POSTGRES_APP_USER`) owns the database/schema and runs migrations and seeding.
- `eca_reader` (or `POSTGRES_READER_USER`) receives connect, schema usage, and SELECT-only table
  privileges. Default privileges grant SELECT on future tables created by the application role.

The backend uses the reader DSN only for generated analytical SQL. It never gives that path the
administrator or owner DSN. Role initialization runs only when PostgreSQL initializes an empty
volume; changing role variables later does not rewrite an existing volume.

Seed deterministic synthetic data explicitly after startup:

```bash
docker compose --env-file .env.docker run --rm seed
```

The existing seed command refuses non-empty target tables, preventing accidental duplicate data.
For an intentional local reset, run:

```bash
docker compose --env-file .env.docker run --rm seed python -m app.db.seed --reset
```

Never use reset against non-development data.

## Health, shared state, and operations

Health checks cover PostgreSQL (`pg_isready`), Redis (`redis-cli ping`), the backend's exact public
`{"status":"ok"}` contract, and the frontend root. Inspect them with:

```bash
docker compose --env-file .env.docker ps
docker compose --env-file .env.docker logs -f backend frontend migrate
```

Sessions use Redis database 0 with the `eca:session` prefix. The shared rate limiter uses Redis
database 1 with the `eca:rate` prefix. Both fail closed on Redis errors; there is no JSON or
in-memory fallback in this stack. Redis URLs contain no password because the service is isolated on
the private Compose network and publishes no host port; production Redis authentication and network
controls remain deployment concerns.

Stop containers without deleting data:

```bash
docker compose --env-file .env.docker down
```

To intentionally destroy all local PostgreSQL and Redis data, first stop the stack and then run:

```bash
docker compose --env-file .env.docker down --volumes
```

## Troubleshooting

- Check `docker compose ... ps` before application logs; `migrate` must show exit code 0.
- If PostgreSQL role values changed after first initialization, recreate the local volumes
  intentionally or restore the original local values.
- If seeding reports populated tables, the safeguard is working. Use the explicit development-only
  reset command only when data loss is intended.
- A missing LLM key does not prevent startup or health checks. LLM-backed operations remain
  unavailable until a provider is configured at runtime.
- Port conflicts can be resolved by changing `FRONTEND_PORT` or `BACKEND_PORT` in `.env.docker`.
