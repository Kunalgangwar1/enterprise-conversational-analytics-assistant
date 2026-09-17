# syntax=docker/dockerfile:1.7

ARG PYTHON_VERSION=3.11
ARG UV_VERSION=0.8.22

FROM ghcr.io/astral-sh/uv:${UV_VERSION} AS uv

FROM python:${PYTHON_VERSION}-slim-bookworm AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app/backend

COPY --from=uv /uv /usr/local/bin/uv
COPY pyproject.toml uv.lock README.md ./

RUN uv sync --locked --no-dev --no-install-project

FROM python:${PYTHON_VERSION}-slim-bookworm AS runtime

ENV PATH="/app/backend/.venv/bin:${PATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN groupadd --system --gid 10001 eca \
    && useradd --system --uid 10001 --gid eca --home-dir /app --shell /usr/sbin/nologin eca

WORKDIR /app/backend

# Official AWS bundle enables verify-full TLS for RDS PostgreSQL connections.
ADD --chmod=0444 https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem /etc/ssl/certs/aws-rds-global-bundle.pem

COPY --from=builder --chown=eca:eca /app/backend/.venv ./.venv
COPY --chown=eca:eca app ./app
COPY --chown=eca:eca config ./config
COPY --chown=eca:eca data ./data
COPY --chown=eca:eca alembic ./alembic
COPY --chown=eca:eca alembic.ini ./alembic.ini

RUN mkdir -p /app/backend/artifacts && chown eca:eca /app/backend/artifacts

USER eca

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=5 \
    CMD ["python", "-c", "import json, urllib.request; response = urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=2); assert json.load(response) == {'status': 'ok'}"]

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
