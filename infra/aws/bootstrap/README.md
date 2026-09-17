# AWS bootstrap layer

This one-time layer creates only the encrypted/versioned/private Terraform state bucket, the
private backend ECR repository, and—after a real repository name is known—the narrowly trusted
GitHub OIDC provider and environment-scoped deployment roles. It intentionally uses local state because an S3 backend
cannot create itself.

Copy `terraform.tfvars.example` to an ignored `terraform.tfvars`, choose a globally unique bucket
name, and run `terraform init`, `terraform plan`, then review before any separately authorized
`terraform apply`. Keep the resulting local bootstrap state encrypted, access-controlled, and
backed up; losing it complicates safe lifecycle management. The application stack uses the bucket
with native S3 lock files and does not create a DynamoDB lock table.

Leave `enable_github_oidc = false` until the exact `owner/repository` exists. When enabled, trust is
restricted to that repository, one exact GitHub environment per role, `refs/heads/main`, and the
`sts.amazonaws.com` audience. Set each GitHub environment's `AWS_DEPLOY_ROLE_ARN` from the matching
entry in the `github_deploy_role_arns` output. For a repository created/transferred after
2026-07-15, configure the
immutable `owner@OWNER_ID/repository@REPO_ID` subject segment shown by GitHub. The role is not an
administrator role, but it can create and remove this project's network and managed-service
resources, so protect branch/workflow controls accordingly.
