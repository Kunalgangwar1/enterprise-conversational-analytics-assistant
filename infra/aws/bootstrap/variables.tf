variable "aws_region" {
  description = "AWS region for bootstrap resources."
  type        = string
  default     = "ap-south-1"
}

variable "project_name" {
  description = "Generic project identifier used for names and tags."
  type        = string
  default     = "enterprise-conversational-analytics"
}

variable "environment" {
  description = "Deployment environment name."
  type        = string
  default     = "dev"
}

variable "state_bucket_name" {
  description = "Globally unique S3 bucket name for application Terraform state."
  type        = string

  validation {
    condition     = length(var.state_bucket_name) >= 3
    error_message = "state_bucket_name must be an explicitly chosen S3 bucket name."
  }
}

variable "ecr_repository_name" {
  description = "Private ECR repository used for immutable backend images."
  type        = string
  default     = "enterprise-conversational-analytics-backend"
}

variable "ecr_image_retention_count" {
  description = "Maximum number of tagged backend images retained."
  type        = number
  default     = 20
}

variable "enable_github_oidc" {
  description = "Create the GitHub OIDC provider and deployment role after a repository is known."
  type        = bool
  default     = false
}

variable "github_repository" {
  description = "Exact GitHub OIDC repository segment: owner/repository or immutable owner@id/repository@id."
  type        = string
  default     = null
  nullable    = true

  validation {
    condition = (
      var.github_repository == null ||
      can(regex("^[A-Za-z0-9_.@-]+/[A-Za-z0-9_.@-]+$", var.github_repository))
    )
    error_message = "github_repository must use the owner/repository form."
  }
}

variable "github_trusted_environments" {
  description = "Exact GitHub environments allowed to request deployment credentials."
  type        = set(string)
  default     = ["dev"]
}

variable "github_trusted_ref" {
  description = "Only this Git ref may assume the deployment role."
  type        = string
  default     = "refs/heads/main"
}
