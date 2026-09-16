# Enterprise Conversational Analytics Assistant

This repository is a clean-room, learning-focused reconstruction of an enterprise conversational
analytics system. It uses synthetic healthcare examples only. Proprietary code, production data,
patient/member data, and credentials must never be committed.

`ARCHITECTURE_REPO_RUNBOOK.md` is the primary reference for the intended system. The implementation
is complete through Phase 25. Phase 18 connects specialist workflows through a thin chat
orchestrator and React One UI, Phase 19 adds the deterministic AI Dashboard, and Phase 20 adds a
sidecar evaluation/regression harness. Phase 21 adds provider-neutral authentication, explicit
RBAC, subject-owned sessions, and deterministic self-access inspection. Phases 22-23 add shared
Redis state and security hardening; Phase 24 adds production-capable images and a local Compose
integration stack. Phase 25 adds cloud-independent GitHub Actions quality gates and versioned GHCR
artifact delivery without deploying to AWS.

## Repository layout

```text
backend/    FastAPI, application workflows, persistence, and tests
frontend/   React/TypeScript One UI and tests
docs/       Architecture, component notes, and ADRs
scripts/    Task-specific utilities
```

## Local full-stack startup

Python 3.11+, Node.js 18+, npm, and a local PostgreSQL instance are expected. Configure local
backend values from `.env.example`; never place secrets in source control.

Local development uses a configured server-side identity and requires no browser token:

```dotenv
APP_ENV=development
AUTH_MODE=development
AUTH_DEV_SUBJECT=dev-user
AUTH_DEV_ROLES=analyst
```

Development authentication is rejected outside local/development/test environments.
Production-style `AUTH_MODE=oidc` verifies signed bearer JWTs using configured issuer JWKS and can
later point at Cognito without changing authorization logic. Phase 21 stores no passwords and
requires no AWS account.

Terminal 1:

```bash
source .venv/bin/activate
cd backend
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Terminal 2:

```bash
cd frontend
npm install
npm run dev
```

The webpack development server proxies `/api` and `/chat` to the backend on port 8000. Open:

- Chat: `http://localhost:5173/#/`
- Dashboard: `http://localhost:5173/#/dashboard`

Both surfaces run in the same React application and backend processes.

The frontend needs no Gemini, Azure, AWS, or database credentials. LLM-backed backend workflows
require their selected provider configuration, while deterministic modes such as Data Discovery
remain usable without model credentials.
The aggregate Dashboard also requires no model or AWS credentials.

## Docker quick start

Docker Compose provides PostgreSQL, Redis, one-shot migrations, the FastAPI backend, and the React
production frontend. It is local integration infrastructure, not the final AWS topology.

```bash
cp .env.docker.example .env.docker
# Replace every local-only placeholder password in .env.docker.
docker compose --env-file .env.docker up -d --build --wait
docker compose --env-file .env.docker run --rm seed  # optional synthetic data
```

Open `http://localhost:5173/#/`. Stop without deleting named volumes using `docker compose
--env-file .env.docker down`. See [`docs/docker.md`](docs/docker.md) for architecture, role setup,
health checks, logs, seeding, and intentional volume reset instructions.

## Evaluation

From `backend/`, run the deterministic network-free profile:

```bash
python -m app.evaluation.run --profile offline
```

Run against the local synthetic PostgreSQL database, or optionally the configured live provider:

```bash
python -m app.evaluation.run --profile integration
python -m app.evaluation.run --profile live
```

Compare a reviewed baseline with `--compare-baseline evals/baselines/offline-v1.json`. Live runs are
never started automatically and do not fall back to fakes. See [`docs/evaluation.md`](docs/evaluation.md).

## CI/CD

Pull requests and `main` pushes run backend, PostgreSQL/Redis integration, frontend, evaluation,
security-audit, Compose, and Docker-build gates. Python 3.11 matches the backend image; Python 3.14
has a weekly/manual compatibility workflow. Semantic version tags publish separate backend and
frontend images to GHCR using the automatic least-privilege `GITHUB_TOKEN`. Normal CI requires no
application or cloud secrets and never runs live LLM evaluation or AWS deployment. See
[`docs/ci-cd.md`](docs/ci-cd.md).

## Database setup

The documented source architecture uses Databricks SQL. This reconstruction uses PostgreSQL as its
local relational and analytical substitute. From `backend/`:

```bash
alembic upgrade head
alembic current
python -m app.db.seed
```

`DATABASE_URL` is for migrations and seeding. The query path requires a separate SELECT-only
`QUERY_DATABASE_URL`; it never falls back to the write-capable URL. See
[`docs/database.md`](docs/database.md).

## Verification

Backend, from `backend/`:

```bash
pytest -m "not integration and not live_llm"
pytest -m integration
ruff check .
ruff format --check .
```

Frontend, from `frontend/`:

```bash
npm run typecheck
npm test
npm run lint
npm run build
```

The main APIs are documented in [`docs/api.md`](docs/api.md), the current architecture in
[`docs/architecture.md`](docs/architecture.md), authentication/RBAC in
[`docs/authentication-authorization.md`](docs/authentication-authorization.md), and its decision in
[`ADR-021`](docs/decisions/ADR-021-authentication-authorization-rbac.md).
