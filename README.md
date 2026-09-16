# Enterprise Conversational Analytics Assistant

This repository is a clean-room, learning-focused reconstruction of an enterprise conversational
analytics system. It uses synthetic healthcare examples only. Proprietary code, production data,
patient/member data, and credentials must never be committed.

`ARCHITECTURE_REPO_RUNBOOK.md` is the primary reference for the intended system. The implementation
is complete through Phase 18: the FastAPI backend connects the existing specialist workflows through
a thin chat orchestrator, and the React/TypeScript/webpack One UI provides the conversational surface.
Phase 19 AI Dashboard functionality is not implemented.

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

Open `http://localhost:5173`. The webpack development server proxies `/api` and `/chat` to the
backend on port 8000. The application uses `HashRouter`, so client routes appear after `#/`.

The frontend needs no Gemini, Azure, AWS, or database credentials. LLM-backed backend workflows
require their selected provider configuration, while deterministic modes such as Data Discovery
remain usable without model credentials.

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
[`docs/architecture.md`](docs/architecture.md), and the Phase 18 decision in
[`ADR-018`](docs/decisions/ADR-018-one-ui-chat-orchestration.md).
