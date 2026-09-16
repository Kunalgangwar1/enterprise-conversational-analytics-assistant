# Backend

This directory contains the Phase 1 FastAPI service foundation.

From this directory, install the backend and development tools with:

```bash
python -m pip install -e ".[dev]"
```

Run the API with:

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Run tests and lint checks with:

```bash
pytest -m "not integration"
ruff check .
```

## Local PostgreSQL

The original architecture uses Databricks SQL; PostgreSQL is only the local reconstruction store.
After configuring the root `.env`, apply the schema and seed synthetic data with:

```bash
alembic upgrade head
alembic current
python -m app.db.seed
```

PostgreSQL integration tests use only `TEST_DATABASE_URL`:

```bash
pytest -m integration
```

See `../docs/database.md` for schema and reset-safety details.

## Internal query execution

Configure `QUERY_DATABASE_URL` with a SELECT-only PostgreSQL role before requesting the internal
query executor. It does not fall back to the owner `DATABASE_URL`. SQL is AST-validated, executed in
a read-only transaction with a local timeout, and fetched with a configured row bound. No HTTP SQL
execution endpoint exists in Phase 4.
