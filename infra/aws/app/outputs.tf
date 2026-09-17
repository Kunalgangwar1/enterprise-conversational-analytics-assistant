output "cloudfront_url" {
  description = "Single public application URL."
  value       = local.cloudfront_url
}

output "cloudfront_distribution_id" {
  description = "CloudFront distribution ID used for invalidations."
  value       = aws_cloudfront_distribution.application.id
}

output "frontend_bucket_name" {
  description = "Private bucket receiving compiled frontend assets."
  value       = aws_s3_bucket.frontend.id
}

output "backend_ecr_repository_url" {
  description = "Private backend image repository."
  value       = data.aws_ecr_repository.backend.repository_url
}

output "ecs_cluster_name" {
  value = aws_ecs_cluster.application.name
}

output "ecs_service_name" {
  value = aws_ecs_service.backend.name
}

output "database_bootstrap_task_definition_arn" {
  value = aws_ecs_task_definition.database_bootstrap.arn
}

output "migration_task_definition_arn" {
  value = aws_ecs_task_definition.migration.arn
}

output "seed_task_definition_arn" {
  description = "Optional synthetic seed task; deployments never run it automatically."
  value       = aws_ecs_task_definition.seed.arn
}

output "ecs_task_subnet_ids" {
  value = local.task_subnet_ids
}

output "ecs_task_security_group_id" {
  value = aws_security_group.backend.id
}

output "ecs_assign_public_ip" {
  value = local.assign_public_ip
}

output "rds_endpoint_hostname" {
  value = aws_db_instance.application.address
}

output "elasticache_endpoint_hostname" {
  value = aws_elasticache_replication_group.application.primary_endpoint_address
}

output "cognito_user_pool_id" {
  value = aws_cognito_user_pool.application.id
}

output "cognito_app_client_id" {
  value = aws_cognito_user_pool_client.spa.id
}

output "cognito_issuer" {
  value = local.cognito_issuer
}

output "cognito_managed_login_domain" {
  value = "https://${aws_cognito_user_pool_domain.application.domain}.auth.${var.aws_region}.amazoncognito.com"
}

output "cloudwatch_dashboard_name" {
  value = aws_cloudwatch_dashboard.operations.dashboard_name
}

output "alarm_sns_topic_arn" {
  description = "Optional un-subscribed alarm topic ARN."
  value       = try(aws_sns_topic.alarms[0].arn, null)
}
