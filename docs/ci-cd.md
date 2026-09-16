# CI/CD automation

Phase 25 adds GitHub Actions and GHCR as clean-room engineering choices for this reconstruction. It
does not claim that the source system used either service, and it does not deploy to AWS.

## Workflow architecture

The main `CI` workflow runs for pull requests, pushes to `main`, and manual dispatches. Newer runs
for the same event/ref cancel obsolete work. Its default token permission is only `contents: read`;
it does not use `pull_request_target` or expose application/cloud secrets to pull-request code.

The required job graph is:

```text
Backend Tests ------> Offline Evaluation
Backend Integration -> Integration Evaluation
Backend Quality --┐
Frontend ---------+-> Docker Build -> Container Smoke (main/manual only)
Security Audit --- independent
```

Stable check names recommended for branch protection are `Backend Quality`, `Backend Tests`,
`Backend Integration`, `Frontend`, `Offline Evaluation`, `Integration Evaluation`, `Docker Build`,
and `Security Audit`. `Container Smoke` is intentionally limited to pushes/manual runs so pull
requests receive image-build validation without paying for a second full Compose build.

All jobs have timeouts. Evaluation JSON and Markdown reports are uploaded for seven days; virtual
environments, `node_modules`, databases, Redis data, and environment files are never uploaded.

## Runtime and dependency policy

Python 3.11 is primary CI because it matches the production-style backend image. A lightweight
`Python Compatibility` workflow runs non-integration tests on the Python 3.14 series every Monday
and on manual dispatch, reflecting the current developer environment without doubling every PR
job. Both use `uv sync --frozen`; CI never rewrites `uv.lock`.

Frontend CI uses Node 22, `npm ci`, type checking, Jest, ESLint, and the webpack production build.
The setup-node cache stores downloaded npm data, not `node_modules`.

## PostgreSQL, Redis, and evaluations

Integration jobs create fresh PostgreSQL 16 and Redis 7.4 service containers with native health
checks. They pass only explicit ephemeral test configuration and do not read `.env`. The Phase 24
PostgreSQL bootstrap script creates `eca_app` for migrations/seeding and separate SELECT-only
`eca_reader` credentials for query execution. Alembic upgrades the empty database and the existing
deterministic synthetic seed supplies integration fixtures, including `M000001`.

The backend integration suite and Phase 20 integration profile use the real reader boundary. The
offline evaluation remains network-free. Evaluator exit codes own pass/fail policy, including all
zero-tolerance privacy, SQL safety, citation, tool, and budget invariants. CI never runs the live
Gemini/Azure profile.

## Docker and container smoke

Pull-request CI validates `compose.yaml` using `.env.docker.example`, then independently builds the
backend and frontend with Buildx without logging into a registry or pushing. Existing
`.dockerignore` files keep `.env`, local virtual environments, `node_modules`, caches, tests, and
generated evaluation/session artifacts out of build contexts.

Pushes to `main` and manual CI runs additionally start the Phase 24 Compose stack, wait on declared
health conditions, check the frontend, exact minimal backend health response, and development-auth
boundary, then shut the stack down. No LLM provider is called.

## Security and dependency maintenance

`Security Audit` exports runtime dependencies from the frozen uv lock to a temporary hashed
requirements file and scans them with isolated `pip-audit==2.10.1`. It also runs `npm audit
--omit=dev --audit-level=high`: high/critical production findings fail, while all lower findings
remain visible. As of 2026-09-17, the Python audit reports no known vulnerabilities. npm reports two
moderate React Router advisories (`GHSA-wrjc-x8rr-h8h6` and `GHSA-337j-9hxr-rhxg`); the suggested
forced fix is breaking and is deliberately not applied automatically.

Dependabot checks uv, npm, GitHub Actions, and both Dockerfile directories weekly, grouping
compatible minor/patch updates. It does not auto-merge. GitHub dependency review is not a required
job because availability depends on repository visibility/security-plan settings; it can be enabled
later without replacing the portable audits.

Workflow actions from GitHub, Docker, and Astral are pinned to immutable commit SHAs resolved from
their official major-version tags. Version comments keep the intended release line reviewable and
allow Dependabot to propose controlled action updates.

## Release images

Pushing a semantic tag such as `v1.0.0` runs `Release Images`. It validates the tag, logs in to GHCR
with the repository-provided `GITHUB_TOKEN`, and publishes separate images:

```text
ghcr.io/<owner>/<repository>-backend
ghcr.io/<owner>/<repository>-frontend
```

Names are derived dynamically and normalized to lowercase. Each image receives the semantic tag
and a full `sha-<commit>` tag plus OCI source, revision, version, and creation metadata. No mutable
`latest` tag is published. The workflow grants only `contents: read` and `packages: write`; it needs
no PAT, application credential, database password, Gemini/Azure key, or AWS credential.

## Repository settings and operations

After pushing to GitHub with Actions enabled, configure branch protection manually:

- require pull requests before merge;
- require the eight stable CI checks listed above;
- optionally block direct pushes, dismiss stale approvals, and require conversation resolution.

These settings are recommendations only; local files cannot prove they were applied. Rerun failed
jobs or whole workflows from the GitHub Actions UI after addressing the failure. Evaluation reports
are available from the failed/successful run's artifacts. For integration failures, inspect service
health and migration output before test output; for Docker failures, reproduce with the commands in
`docs/docker.md`.

Normal Phase 25 CI requires no repository secrets. GHCR uses the automatic `GITHUB_TOKEN`. Phase 26
should use GitHub OIDC and short-lived AWS roles where feasible, never long-lived AWS access keys.
Phase 25 creates no ECR, ECS, RDS, ElastiCache, ALB, Cognito, VPC, IAM, DNS, certificate, or
infrastructure-as-code resource.
