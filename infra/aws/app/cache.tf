resource "aws_elasticache_subnet_group" "application" {
  name       = "${local.name_prefix}-cache"
  subnet_ids = values(aws_subnet.private_data)[*].id
}

ephemeral "random_password" "cache" {
  length  = 48
  special = false
}

resource "aws_elasticache_replication_group" "application" {
  replication_group_id = "${local.name_prefix}-valkey"
  description          = "Shared TLS session and rate-limit state"

  engine                     = "valkey"
  engine_version             = var.cache_engine_version
  node_type                  = var.cache_node_type
  port                       = local.cache_port
  num_cache_clusters         = 1
  automatic_failover_enabled = false
  multi_az_enabled           = false
  subnet_group_name          = aws_elasticache_subnet_group.application.name
  security_group_ids         = [aws_security_group.cache.id]
  at_rest_encryption_enabled = true
  transit_encryption_enabled = true
  transit_encryption_mode    = "required"
  auth_token_wo              = ephemeral.random_password.cache.result
  auth_token_wo_version      = var.cache_secret_version
  apply_immediately          = true
  snapshot_retention_limit   = 0
}

resource "aws_secretsmanager_secret" "cache" {
  name                    = "${local.name_prefix}/cache/runtime"
  description             = "TLS Valkey URLs for sessions and rate limiting"
  recovery_window_in_days = var.secret_recovery_window_days
}

resource "aws_secretsmanager_secret_version" "cache" {
  secret_id = aws_secretsmanager_secret.cache.id
  secret_string_wo = jsonencode({
    session_redis_url = join("", [
      "rediss://:",
      urlencode(ephemeral.random_password.cache.result),
      "@${aws_elasticache_replication_group.application.primary_endpoint_address}:${local.cache_port}/0",
    ])
    rate_limit_redis_url = join("", [
      "rediss://:",
      urlencode(ephemeral.random_password.cache.result),
      "@${aws_elasticache_replication_group.application.primary_endpoint_address}:${local.cache_port}/1",
    ])
  })
  secret_string_wo_version = var.cache_secret_version
}
