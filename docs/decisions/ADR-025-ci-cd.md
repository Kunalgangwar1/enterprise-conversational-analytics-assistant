# ADR-025: GitHub Actions CI and GHCR artifact delivery

- Status: Accepted
- Date: 2026-09-17

## Context

The reconstruction has deterministic tests, PostgreSQL/Redis integration boundaries, objective
evaluation gates, and independently buildable images. Manually running these checks is not enough
to prevent regressions or produce traceable release artifacts. Phase 26 has not selected or created
AWS infrastructure.

GitHub Actions and GHCR are clean-room implementation choices; they are not attributed to the
source system.

## Decision

Use GitHub Actions for pull-request and `main` validation with least-privilege, cloud-independent
jobs. Python 3.11 is the primary runtime-parity version. Python 3.14 receives a scheduled/manual
compatibility run rather than duplicating every routine job.

Required CI covers backend quality and non-integration tests, isolated PostgreSQL/Redis integration
with migrations and synthetic seeding, Phase 20 offline/integration evaluation, frontend quality
and build, dependency audits, Compose validation, and independent image builds. Live LLM evaluation
is excluded. A small Compose smoke runs only on `main` pushes and manual CI.

Dependabot proposes grouped weekly uv, npm, GitHub Actions, and Docker updates without auto-merge.
Version tags publish separate backend/frontend images to GHCR using the automatic `GITHUB_TOKEN`
with `contents: read` and `packages: write`. Images receive semantic-version and full commit-SHA
tags plus OCI metadata; no `latest`-only policy is used. Third-party workflow actions are limited to
GitHub, Docker, and Astral and pinned to commits resolved from their official release tags.

No AWS login or deployment is performed. Phase 26 should prefer GitHub OIDC with short-lived AWS
roles over long-lived access keys.

## Alternatives considered

- Manual-only validation: rejected because it is inconsistent and cannot enforce merge gates.
- CI requiring Gemini or another paid provider: rejected because PRs must be deterministic,
  cloud-independent, and safe for untrusted contributions.
- Deploying every pull request: rejected because deployment architecture and authorization belong
  to Phase 26.
- Publishing only `latest`: rejected because it is mutable and does not identify source revisions.
- Using a production/shared database in CI: rejected in favor of disposable health-checked services
  containing only deterministic synthetic data.
- Using a long-lived registry PAT when `GITHUB_TOKEN` suffices: rejected as unnecessary secret
  exposure.
- Using long-lived AWS access keys: rejected; Phase 26 should establish OIDC federation.
- Skipping integration or evaluation gates: rejected because unit tests alone do not validate
  database permissions, result equivalence, retrieval quality, or zero-tolerance invariants.

## Consequences

Every proposed or merged change can receive consistent quality, integration, evaluation, security,
and image-build feedback without application secrets. Release tags can produce traceable pre-AWS
artifacts, while actual infrastructure and deployment remain deliberately unimplemented.

GitHub runner usage increases, action pins require ongoing supply-chain review, dependency audits
depend on public advisory services, and repository administrators must configure branch protection
after a GitHub remote exists.
