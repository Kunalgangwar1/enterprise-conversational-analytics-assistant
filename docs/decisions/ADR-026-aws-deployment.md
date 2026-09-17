# ADR-026: Terraform-managed AWS deployment

- Status: Accepted
- Date: 2026-09-17

## Context

The reconstruction has production-capable containers, cloud-independent CI, provider-neutral OIDC,
shared Redis state, and PostgreSQL role separation. It needs a reviewable AWS topology without
silently creating billable infrastructure, exposing data services, weakening Phase 23 controls, or
introducing long-lived deployment credentials.

AWS infrastructure is a clean-room engineering choice and is not attributed to the source system.

## Decision

Use Terraform 1.11+ with the official bounded 6.x AWS provider. A local bootstrap layer creates an
encrypted/versioned/private S3 state bucket, an immutable/scanned backend ECR repository, and an
optional exact-repository/environment/ref GitHub OIDC roles, including GitHub's immutable subject
format when applicable. Each environment receives a separately trusted and IAM-prefix-scoped role.
Application state uses native S3 lock files rather than DynamoDB. Generated
database/cache credentials use ephemeral random values and provider
write-only arguments where supported; state remains sensitive operational data.

CloudFront is the single public endpoint. A private S3 bucket with OAC serves React assets. `/api/*`
and `/chat*` reach an internal ALB through CloudFront VPC Origin. ECS Fargate runs one SHA-tagged
backend task by default. The execution role pulls images, logs, and reads referenced secrets. The
application task role has no AWS permissions unless the optional Phase 27 ADOT sidecar is enabled,
in which case a separate narrow telemetry export policy is attached.

ALB target probes use private target IPs as their HTTP `Host`. The trusted-host middleware therefore
allows RFC 1918/loopback hosts only for `GET /api/health`; all other routes retain the explicit host
allowlist, and the health response contains no infrastructure detail.

RDS PostgreSQL 16 and TLS Valkey occupy private data subnets and accept only the backend task security
group. RDS manages its master secret. A bounded idempotent task creates `eca_app` and SELECT-only
`eca_reader`; separate one-shot tasks migrate and optionally seed synthetic demo data. Normal tasks
never receive the master credential. Secrets Manager supplies runtime DSNs and optional Gemini
credentials. RDS connections verify the official AWS CA bundle and Valkey uses `rediss://`.

Cognito provides a secretless SPA client, managed login, authorization-code flow with PKCE, and
viewer/analyst/admin groups. Browser tokens remain in memory. The backend validates Cognito access
token `client_id` and `token_use` while preserving standard audience-based OIDC compatibility.

GitHub deployment is manual, plan-only by default, and uses OIDC with `contents: read` and
`id-token: write`. Explicit apply runs publish a full-commit-SHA backend image, apply a saved plan,
run bootstrap/migrations, upload the static frontend, invalidate CloudFront, and smoke-test. No
long-lived AWS keys and no automatic seed are used.

Cost-aware development uses one task, small single-AZ data services, no autoscaling/WAF, short log
retention, and public-subnet tasks with locked-down ingress to avoid NAT cost. Private task subnets
plus NAT are an explicit production-oriented mode.

## Alternatives considered

- Public ALB or public ECS application port: rejected because CloudFront must be the only public
  application route.
- Public S3 website, RDS, or ElastiCache: rejected because each bypasses required private boundaries.
- EC2 or EKS: rejected as unnecessary operational complexity for the current learning deployment.
- Frontend in ECR/ECS: rejected in favor of private S3 and CloudFront; the image remains for local use.
- Long-lived AWS access keys or registry PATs: rejected in favor of GitHub OIDC and AWS/GitHub native
  short-lived credentials.
- One database superuser: rejected because generated SQL must remain on `eca_reader`.
- DynamoDB Terraform locking: rejected because native S3 lock files are available.
- NAT Gateway in every environment: rejected because cost-optimized learning mode can safely use
  public task egress without public application ingress.
- Bedrock migration, autoscaling, WAF, and multi-region reliability: deferred to later phases.
  Phase 27 subsequently adds an optional dashboard and initial operational alarms.

## Consequences

The topology is reproducible and reviewable, preserves existing security boundaries, and can deploy
without application secrets in GitHub. It introduces AWS charges and operational responsibility for
state, secrets, certificate bundles, backups, image retention, Cognito users, and deletion controls.
The default topology is not highly available or production-sized. Terraform/provider availability,
AWS credentials, a real GitHub repository, a reviewed plan, and explicit apply authorization remain
prerequisites for live deployment.
