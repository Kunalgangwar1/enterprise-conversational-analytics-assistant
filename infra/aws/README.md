# AWS infrastructure

`bootstrap/` is the one-time local-state layer for the remote-state bucket, backend ECR repository,
and optional GitHub OIDC deployment role. `app/` is the remotely stored application stack.

Start with `docs/aws-deployment.md`. No command in these directories should be treated as approval
to create resources: review a saved Terraform plan and the cost/data-loss implications first.
