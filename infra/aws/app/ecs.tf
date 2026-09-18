data "aws_ecr_repository" "backend" {
  name = var.backend_ecr_repository_name
}

resource "aws_cloudwatch_log_group" "backend" {
  name              = "/ecs/${local.name_prefix}/backend"
  retention_in_days = var.log_retention_days
}

resource "aws_ecs_cluster" "application" {
  name = "${local.name_prefix}-cluster"

  setting {
    name  = "containerInsights"
    value = var.enable_container_insights ? "enabled" : "disabled"
  }
}

locals {
  backend_image = "${data.aws_ecr_repository.backend.repository_url}:${var.backend_image_tag}"
  common_environment = [
    { name = "APP_ENV", value = "production" },
    { name = "AUTH_MODE", value = "oidc" },
    { name = "AUTH_OIDC_ISSUER", value = local.cognito_issuer },
    { name = "AUTH_OIDC_JWKS_URL", value = "${local.cognito_issuer}/.well-known/jwks.json" },
    { name = "AUTH_OIDC_CLIENT_ID", value = aws_cognito_user_pool_client.spa.id },
    { name = "AUTH_OIDC_CLIENT_ID_CLAIM", value = "client_id" },
    { name = "AUTH_OIDC_TOKEN_USE", value = "access" },
    { name = "AUTH_OIDC_GROUPS_CLAIM", value = "cognito:groups" },
    { name = "AUTH_GROUP_ROLE_MAPPING", value = jsonencode({ viewer = "viewer", analyst = "analyst", admin = "admin" }) },
    { name = "APP_HOST", value = "0.0.0.0" },
    { name = "APP_PORT", value = tostring(local.backend_port) },
    { name = "LOG_LEVEL", value = "INFO" },
    { name = "LOG_FORMAT", value = "json" },
    { name = "SERVICE_NAME", value = var.service_name },
    { name = "SERVICE_VERSION", value = var.backend_image_tag },
    { name = "ALLOWED_HOSTS", value = jsonencode([aws_cloudfront_distribution.application.domain_name, aws_lb.backend.dns_name]) },
    { name = "CORS_ALLOWED_ORIGINS", value = jsonencode([local.cloudfront_url]) },
    { name = "CORS_ALLOW_CREDENTIALS", value = "true" },
    { name = "SECURITY_HEADERS_ENABLED", value = "true" },
    { name = "HSTS_ENABLED", value = "true" },
    { name = "API_DOCS_ENABLED", value = "false" },
    { name = "SESSION_COOKIE_SECURE", value = "true" },
    { name = "SESSION_STORE_BACKEND", value = "redis" },
    { name = "RATE_LIMIT_ENABLED", value = "true" },
    { name = "RATE_LIMIT_BACKEND", value = "redis" },
    { name = "DATABASE_POOL_SIZE", value = tostring(var.database_pool_size) },
    { name = "DATABASE_MAX_OVERFLOW", value = tostring(var.database_max_overflow) },
    { name = "DATABASE_POOL_RECYCLE_SECONDS", value = tostring(var.database_pool_recycle_seconds) },
    { name = "KNOWLEDGE_CATALOG_DIR", value = "/app/backend/data/knowledge_catalog" },
    { name = "DATA_QUALITY_DIR", value = "/app/backend/data/data_quality" },
    { name = "ARTIFACTS_OUTPUT_DIR", value = "/tmp/eca-artifacts" },
  ]
  observability_environment = concat(
    [{ name = "OBSERVABILITY_ENABLED", value = tostring(var.observability_enabled) }],
    var.observability_enabled ? [
      { name = "OTEL_EXPORTER_OTLP_ENDPOINT", value = "http://127.0.0.1:4318" },
      { name = "OTEL_EXPORTER_OTLP_PROTOCOL", value = "http/protobuf" },
      { name = "OTEL_TRACE_SAMPLE_RATIO", value = tostring(var.otel_trace_sample_ratio) },
      { name = "OTEL_EXPORT_TIMEOUT_SECONDS", value = "5" },
      { name = "METRICS_ENABLED", value = "true" },
      { name = "TRACING_ENABLED", value = "true" },
    ] : [],
  )
  runtime_secrets = concat(
    [
      { name = "DATABASE_URL", valueFrom = "${aws_secretsmanager_secret.application_database.arn}:database_url::" },
      { name = "QUERY_DATABASE_URL", valueFrom = "${aws_secretsmanager_secret.application_database.arn}:query_database_url::" },
      { name = "SESSION_REDIS_URL", valueFrom = "${aws_secretsmanager_secret.cache.arn}:session_redis_url::" },
      { name = "RATE_LIMIT_REDIS_URL", valueFrom = "${aws_secretsmanager_secret.cache.arn}:rate_limit_redis_url::" },
    ],
    var.gemini_secret_arn == null ? [] : [
      { name = "GEMINI_API_KEY", valueFrom = var.gemini_secret_arn },
    ],
  )
  log_configuration = {
    logDriver = "awslogs"
    options = {
      awslogs-group         = aws_cloudwatch_log_group.backend.name
      awslogs-region        = var.aws_region
      awslogs-stream-prefix = "backend"
    }
  }
  adot_log_configuration = {
    logDriver = "awslogs"
    options = {
      awslogs-group         = try(aws_cloudwatch_log_group.adot[0].name, "")
      awslogs-region        = var.aws_region
      awslogs-stream-prefix = "adot"
    }
  }
}

resource "aws_ecs_task_definition" "backend" {
  family                   = "${local.name_prefix}-backend"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = tostring(var.ecs_cpu)
  memory                   = tostring(var.ecs_memory)
  execution_role_arn       = aws_iam_role.task_execution.arn
  task_role_arn            = aws_iam_role.task.arn

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }

  container_definitions = jsonencode(concat(
    [{
      name         = "backend"
      image        = local.backend_image
      essential    = true
      command      = ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", tostring(var.backend_worker_processes)]
      environment  = concat(local.common_environment, local.observability_environment)
      secrets      = local.runtime_secrets
      dependsOn = var.observability_enabled ? [{
        containerName = "adot-collector"
        condition     = "START"
      }] : []
      linuxParameters = { initProcessEnabled = true }
      portMappings = [{
        name          = "http"
        containerPort = local.backend_port
        hostPort      = local.backend_port
        protocol      = "tcp"
      }]
      healthCheck = {
        command = [
          "CMD-SHELL",
          "python -c \"import json,urllib.request; r=urllib.request.urlopen('http://127.0.0.1:8000/api/health',timeout=2); assert json.load(r)=={'status':'ok'}\"",
        ]
        interval    = 15
        timeout     = 5
        retries     = 3
        startPeriod = 20
      }
      logConfiguration = local.log_configuration
    }],
    var.observability_enabled ? [{
      name              = "adot-collector"
      image             = var.adot_collector_image
      essential         = false
      cpu               = 128
      memoryReservation = 256
      command           = ["--config=env:AOT_CONFIG_CONTENT"]
      environment = [
        { name = "AWS_REGION", value = var.aws_region },
      ]
      secrets = [{
        name      = "AOT_CONFIG_CONTENT"
        valueFrom = aws_ssm_parameter.adot_config[0].arn
      }]
      portMappings = [{
        name          = "otlp-http"
        containerPort = 4318
        hostPort      = 4318
        protocol      = "tcp"
      }]
      logConfiguration = local.adot_log_configuration
    }] : [],
  ))
}

resource "aws_ecs_task_definition" "database_bootstrap" {
  family                   = "${local.name_prefix}-database-bootstrap"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = tostring(var.ecs_cpu)
  memory                   = tostring(var.ecs_memory)
  execution_role_arn       = aws_iam_role.task_execution.arn
  task_role_arn            = aws_iam_role.task.arn

  container_definitions = jsonencode([{
    name      = "database-bootstrap"
    image     = local.backend_image
    essential = true
    command   = ["python", "-m", "app.db.bootstrap_roles"]
    environment = [
      { name = "DB_BOOTSTRAP_HOST", value = aws_db_instance.application.address },
      { name = "DB_BOOTSTRAP_PORT", value = tostring(local.database_port) },
      { name = "DB_BOOTSTRAP_DATABASE", value = var.database_name },
      { name = "POSTGRES_APP_USER", value = "eca_app" },
      { name = "POSTGRES_READER_USER", value = "eca_reader" },
      { name = "DB_SSLROOTCERT", value = local.rds_ca_bundle },
    ]
    secrets = [
      { name = "DB_BOOTSTRAP_ADMIN_USERNAME", valueFrom = "${aws_db_instance.application.master_user_secret[0].secret_arn}:username::" },
      { name = "DB_BOOTSTRAP_ADMIN_PASSWORD", valueFrom = "${aws_db_instance.application.master_user_secret[0].secret_arn}:password::" },
      { name = "POSTGRES_APP_PASSWORD", valueFrom = "${aws_secretsmanager_secret.application_database.arn}:app_password::" },
      { name = "POSTGRES_READER_PASSWORD", valueFrom = "${aws_secretsmanager_secret.application_database.arn}:reader_password::" },
    ]
    logConfiguration = local.log_configuration
  }])
}

resource "aws_ecs_task_definition" "migration" {
  family                   = "${local.name_prefix}-migration"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = tostring(var.ecs_cpu)
  memory                   = tostring(var.ecs_memory)
  execution_role_arn       = aws_iam_role.task_execution.arn
  task_role_arn            = aws_iam_role.task.arn

  container_definitions = jsonencode([{
    name             = "migration"
    image            = local.backend_image
    essential        = true
    command          = ["alembic", "upgrade", "head"]
    environment      = local.common_environment
    secrets          = local.runtime_secrets
    logConfiguration = local.log_configuration
  }])
}

resource "aws_ecs_task_definition" "seed" {
  family                   = "${local.name_prefix}-seed"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = tostring(var.ecs_cpu)
  memory                   = tostring(var.ecs_memory)
  execution_role_arn       = aws_iam_role.task_execution.arn
  task_role_arn            = aws_iam_role.task.arn

  container_definitions = jsonencode([{
    name             = "seed"
    image            = local.backend_image
    essential        = true
    command          = ["python", "-m", "app.db.seed"]
    environment      = local.common_environment
    secrets          = local.runtime_secrets
    logConfiguration = local.log_configuration
  }])
}

resource "aws_ecs_service" "backend" {
  name            = "${local.name_prefix}-backend"
  cluster         = aws_ecs_cluster.application.id
  task_definition = aws_ecs_task_definition.backend.arn
  desired_count   = var.ecs_desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = local.task_subnet_ids
    security_groups  = [aws_security_group.backend.id]
    assign_public_ip = local.assign_public_ip
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.backend.arn
    container_name   = "backend"
    container_port   = local.backend_port
  }

  health_check_grace_period_seconds = 60
  depends_on                        = [aws_lb_listener.backend]
}
