# AWS deployment

Phase 26 implements a clean-room AWS pre-deployment architecture. Infrastructure code is ready for
review, but creating it is a separate, explicitly authorized operation. RDS, ElastiCache, ALB,
Fargate, NAT Gateway when selected, CloudFront, Secrets Manager, data transfer, and related services
can incur charges. This topology is not claimed to fit entirely within AWS free tiers.

## Architecture

```text
Browser -> CloudFront (only public application endpoint)
             |-- private S3 + OAC (React assets)
             `-- /api/* and /chat* -> VPC origin -> internal ALB -> ECS Fargate
                                                               |-> private RDS PostgreSQL 16
                                                               |-> private ElastiCache Valkey/TLS
                                                               `-> external LLM over HTTPS

Browser -> Cognito managed login -> authorization code + PKCE -> access token
GitHub Actions -> GitHub OIDC -> scoped AWS deployment role -> ECR/Terraform/deployment
```

GitHub Actions, GHCR from Phase 25, Terraform, and the AWS services above are reconstruction
choices; they are not attributed to the source system. The AWS runtime uses the private ECR backend
image. The Phase 24 frontend image remains useful locally, while AWS serves compiled frontend files
from private S3.

## Before any deployment

Install Terraform 1.11 or later and AWS CLI yourself, authenticate to the intended non-production
AWS account, confirm the account with `aws sts get-caller-identity`, and choose a supported region.
`ap-south-1` is the example, not an application hard-code. Review account quotas, especially the
CloudFront managed prefix-list security-group weight.

Never commit real `terraform.tfvars`, state, plans, `.env`, keys, tokens, or passwords. The ignore
rules cover local Terraform state and variable files but deliberately do not ignore provider lock
files. No AWS resources should be created until both bootstrap and application plans are reviewed.

## One-time bootstrap

The S3 backend cannot create itself. `infra/aws/bootstrap` therefore starts with protected local
state and manages only:

- a versioned, encrypted, public-blocked state bucket;
- an immutable, scan-on-push backend ECR repository with bounded retention;
- optionally, the GitHub OIDC provider and one scoped deployment role per trusted environment.

Copy `bootstrap/terraform.tfvars.example` to an ignored `terraform.tfvars`, provide a globally
unique state bucket, and initially keep GitHub OIDC disabled because this repository currently has
no GitHub remote. Run `terraform init`, `terraform validate`, and `terraform plan`. Apply only after
separate approval. Back up and tightly protect the local bootstrap state; migrate it only through a
reviewed state procedure.

Once a real repository exists, set `enable_github_oidc = true`. GitHub environment jobs put the
environment—not the branch—in the default `sub`, so the trust policy requires exact environment
subjects and separately requires the `refs/heads/main` claim. Repositories created or transferred
after 2026-07-15 use an immutable `owner@OWNER_ID/repository@REPO_ID` segment; configure that exact
value after inspecting the repository's OIDC format. The policy accepts only `sts.amazonaws.com`
and never trusts `repo:*/*`. Each role can manage only IAM roles/policies prefixed for its own
environment. The deployment roles have project deployment capabilities but not
`AdministratorAccess`. Configure each GitHub environment's `AWS_DEPLOY_ROLE_ARN` from the matching
`github_deploy_role_arns` bootstrap output.

## Remote state

The application stack uses the bootstrap S3 bucket with encryption and native `use_lockfile = true`
locking. DynamoDB locking is intentionally absent. Initialize with explicit backend arguments:

```bash
terraform -chdir=infra/aws/app init \
  -backend-config="bucket=REPLACE_STATE_BUCKET" \
  -backend-config="key=enterprise-analytics/dev/terraform.tfstate" \
  -backend-config="region=ap-south-1" \
  -backend-config="encrypt=true" \
  -backend-config="use_lockfile=true"
```

State is sensitive even though generated database/cache credentials use ephemeral random values and
Terraform 1.11 write-only provider arguments. RDS manages its master password in Secrets Manager,
and application/cache secret payloads are not persisted in plan/state. State still contains resource
identifiers, endpoints, policies, and other operational metadata, so encryption and least-privilege
access remain mandatory.

## Network and compute

The dedicated VPC spans two Availability Zones with public, private application, and isolated
private data subnets. The internal ALB lives in private application subnets. Its port 80 ingress is
limited to the AWS-managed CloudFront origin-facing prefix list; backend port 8000 accepts only the
ALB security group. RDS 5432 and Valkey 6379 accept only the backend task security group. RDS,
Valkey, the ALB, and S3 are never public.

`ecs_egress_mode` makes the cost/security tradeoff explicit:

- `cost_optimized`: tasks use public subnets and public IPs for outbound AWS/LLM HTTPS access, but
  have no internet-facing application ingress. No NAT Gateway is created.
- `private`: tasks use private application subnets and one NAT Gateway. Use this as the production
  baseline and review higher-availability/VPC-endpoint choices later.

The development baseline is one 0.5-vCPU/1-GiB Fargate task, no autoscaling, one small RDS instance,
one small Valkey node, single-AZ database, no WAF, and seven-day logs. These are practice defaults,
not production sizing or high availability. Phase 27 adds optional ADOT, CloudWatch metrics/logs,
X-Ray traces, a dashboard, and focused alarms; Phase 28 owns reliability and Phase 29 owns scaling.

The ECS execution role pulls ECR images, writes logs, and reads only referenced secrets or the
non-secret ADOT configuration. The ECS task role has no AWS API permissions by default; when
observability is enabled it gains only X-Ray write and application-metric log-stream permissions.
The image is always selected by full
`sha-<40-character-commit>` tag—never `latest`. ALB and container health checks use `/api/health`.
Trusted-host enforcement remains active for application routes; only `GET /api/health` accepts the
private RFC 1918 or loopback IP `Host` values used by ALB/ECS probes, and the response remains the
minimal `{"status":"ok"}` payload.

## Data services and controlled tasks

RDS runs encrypted PostgreSQL 16 in private data subnets, with `rds.force_ssl`, backups, configurable
deletion protection/final snapshots, and an RDS-managed master secret. The backend image includes
the official AWS RDS global CA bundle, and all application/bootstrap DSNs use `sslmode=verify-full`.

The one-shot database bootstrap task uses the master secret only to idempotently create/rotate:

- `eca_app`, owner used for migrations and application writes;
- `eca_reader`, granted schema usage and SELECT on present/future `eca_app` tables.

Normal backend and Alembic tasks never receive the master credential. Generated SQL continues to
use the reader DSN. Run the migration task once per deployment after bootstrap. A separate seed task
exists but is never run automatically; invoke it explicitly only for synthetic dev/demo data.

ElastiCache uses a private, at-rest encrypted, in-transit encrypted Valkey replication group. Its
auth token is write-only, and the backend receives only `rediss://` session and rate-limit URLs.

## Frontend, CloudFront, and Cognito

The frontend bucket blocks all public access and grants `s3:GetObject` only to the distribution via
Origin Access Control. CloudFront redirects viewers to HTTPS, serves `index.html` with short/no-cache
semantics, caches hashed `assets/*` for longer, and adds HSTS, nosniff, frame denial, referrer, and
permissions headers. A CSP is deliberately deferred until it can be tested against Cognito. The
default CloudFront certificate avoids requiring Route 53 or a custom domain.

`/api/*` and `/chat*` use the internal ALB VPC origin with caching disabled. Authorization,
Content-Type, X-Tab-Id, cookies, and query strings reach the origin. Because frontend and API share
one CloudFront host, browser API calls remain same-origin and the secure HttpOnly SameSite=Lax
session cookie works through CloudFront.

Cognito creates a user pool, managed-login domain, secretless SPA client, and `viewer`, `analyst`,
and `admin` groups. Only authorization-code flow with PKCE and `openid email profile` scopes is
enabled. Redirect/logout URLs use the fragment-free CloudFront root; HashRouter resumes after the
callback is cleaned from browser history.

The frontend uses `oidc-client-ts`. Access/refresh tokens use an in-memory user store and are never
written to localStorage or sessionStorage. Only short-lived PKCE transaction state uses
sessionStorage. Refreshing the page can require another login. The centralized API client attaches
the bearer token. Backend verification enforces RS256 signature, issuer, time claims, `token_use =
access`, and `client_id` equal to the SPA client. `cognito:groups` maps only the three known groups;
unknown groups grant nothing. Generic standard-`aud` OIDC verification remains supported.

Terraform creates no users or passwords. To create a synthetic demo identity after deployment, use
the Cognito console or commands like these with reviewed placeholders; do not record a password in
shell history or Terraform:

```bash
aws cognito-idp admin-create-user --user-pool-id USER_POOL_ID --username DEMO_EMAIL
aws cognito-idp admin-add-user-to-group \
  --user-pool-id USER_POOL_ID --username DEMO_EMAIL --group-name analyst
```

## Secrets and external providers

Database role material and Valkey URLs live in Secrets Manager and enter ECS through task-definition
secret references, not plaintext environment entries. An optional existing `gemini_secret_arn`
injects the Gemini key; leaving it unset keeps infrastructure planable and deterministic endpoints
usable. If it uses a customer KMS key, also grant the configured key ARN. Azure support remains
unchanged and no Azure resources or Bedrock migration are included.

Never put secret values in Terraform variables, GitHub variables, workflow YAML, images, or frontend
build settings. Frontend settings—issuer, client ID, login domain, and application URL—are public
OIDC metadata, not secrets.

## Manual GitHub deployment

Bootstrap must exist first. Configure these GitHub repository/environment variables:

- `AWS_REGION`
- `AWS_DEPLOY_ROLE_ARN`
- `AWS_BACKEND_ECR_REPOSITORY`
- `TF_STATE_BUCKET`
- `TF_STATE_KEY`

`.github/workflows/deploy-aws.yml` is manual only. It has `contents: read` and `id-token: write`, uses
short-lived GitHub OIDC credentials, and defaults to a plan-only run. An explicit `apply=true`
dispatch builds/pushes the immutable backend image, applies the saved plan, runs role bootstrap and
Alembic tasks, builds the SPA with public Cognito values, syncs it to private S3, invalidates
CloudFront, and checks the frontend and `/api/health`. It never seeds data. Protect production with
a GitHub environment and required reviewers before enabling apply runs.

For a first local application plan, copy `app/terraform.tfvars.example` to an ignored file, replace
the image placeholder with an ECR tag that actually exists for deployment, initialize remote state,
validate, and save a plan. Do not apply until every public/private boundary and cost-bearing resource
has been reviewed.

## Troubleshooting and smoke checks

- VPC-origin creation: verify region support, ALB `active` status, the CloudFront managed prefix
  list, and security-group quota.
- ECS pull/start failure: inspect task stop reasons and `/ecs/<environment>/backend` logs; verify the
  immutable ECR tag and execution-role secret access.
- Database TLS failure: verify the image contains the current AWS RDS bundle and DSNs retain
  `sslmode=verify-full`; never fall back silently to plaintext or unverified TLS.
- Authentication failure: compare Cognito issuer, `client_id`, `token_use`, and group claim; never
  disable client validation.
- Empty UI: confirm `index.html` was uploaded no-cache and invalidate CloudFront after deployment.
- Smoke checks: request the CloudFront root and confirm `/api/health` returns exactly
  `{"status":"ok"}`. Login through Cognito, then verify `/api/auth/me` without logging tokens.

## Destruction and production differences

`terraform destroy` is documented for deliberate teardown but must never be automated casually.
Destroying RDS, S3 objects/buckets, cache state, secrets, or local bootstrap state can permanently
destroy data. `frontend_force_destroy = false` and state-bucket `prevent_destroy` provide deliberate
friction. Use deletion protection, final snapshots, retention policies, backups, and explicit data
export/approval for production.

Production should start from `terraform.tfvars.production.example`, use private ECS egress, Multi-AZ
RDS, deletion protection, final snapshots, protected GitHub environments, stronger backup/retention
policies, reviewed observability thresholds, and reviewed capacity. WAF, custom
domains/certificates, VPC endpoints, multi-NAT design, autoscaling, disaster recovery, and
multi-region architecture remain outside Phase 26/27.
