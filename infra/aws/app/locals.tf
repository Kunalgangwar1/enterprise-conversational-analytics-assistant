locals {
  name_prefix = "eca-${var.environment}"
  availability_zones = slice(data.aws_availability_zones.available.names, 0, 2)
  az_map             = { for index, az in local.availability_zones : az => index }

  cloudfront_url    = "https://${aws_cloudfront_distribution.application.domain_name}"
  cognito_issuer    = "https://cognito-idp.${var.aws_region}.amazonaws.com/${aws_cognito_user_pool.application.id}"
  rds_ca_bundle     = "/etc/ssl/certs/aws-rds-global-bundle.pem"
  database_port     = 5432
  backend_port      = 8000
  cache_port        = 6379
  ecs_public_mode   = var.ecs_egress_mode == "cost_optimized"
  task_subnet_ids   = local.ecs_public_mode ? values(aws_subnet.public)[*].id : values(aws_subnet.private_app)[*].id
  assign_public_ip  = local.ecs_public_mode
  cognito_domain    = coalesce(var.cognito_domain_prefix, "${local.name_prefix}-${data.aws_caller_identity.current.account_id}")
}
