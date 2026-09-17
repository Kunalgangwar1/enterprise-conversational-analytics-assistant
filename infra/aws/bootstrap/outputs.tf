output "terraform_state_bucket" {
  description = "S3 bucket used by the application stack backend."
  value       = aws_s3_bucket.terraform_state.id
}

output "backend_ecr_repository_name" {
  description = "Backend ECR repository name."
  value       = aws_ecr_repository.backend.name
}

output "backend_ecr_repository_url" {
  description = "Backend ECR repository URL."
  value       = aws_ecr_repository.backend.repository_url
}

output "github_deploy_role_arns" {
  description = "OIDC deployment role ARN keyed by trusted environment."
  value       = { for environment, role in aws_iam_role.github_deploy : environment => role.arn }
}
