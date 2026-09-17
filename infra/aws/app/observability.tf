resource "aws_cloudwatch_log_group" "adot" {
  count = var.observability_enabled ? 1 : 0

  name              = "/ecs/${local.name_prefix}/adot"
  retention_in_days = var.log_retention_days
}

resource "aws_cloudwatch_log_group" "application_metrics" {
  count = var.observability_enabled ? 1 : 0

  name              = "/ecs/${local.name_prefix}/application-metrics"
  retention_in_days = var.log_retention_days
}

resource "aws_ssm_parameter" "adot_config" {
  count = var.observability_enabled ? 1 : 0

  name        = "/${local.name_prefix}/observability/adot-config"
  description = "Non-secret ADOT collector pipeline configuration"
  type        = "String"
  value = <<-YAML
    receivers:
      otlp:
        protocols:
          http:
            endpoint: 0.0.0.0:4318
    processors:
      memory_limiter:
        check_interval: 5s
        limit_mib: 128
        spike_limit_mib: 32
      batch:
        timeout: 5s
        send_batch_size: 128
    exporters:
      awsxray:
        region: $${env:AWS_REGION}
      awsemf:
        region: $${env:AWS_REGION}
        namespace: ${var.application_metric_namespace}
        log_group_name: ${aws_cloudwatch_log_group.application_metrics[0].name}
        log_stream_name: adot-metrics
        dimension_rollup_option: NoDimensionRollup
        resource_to_telemetry_conversion:
          enabled: true
    service:
      telemetry:
        logs:
          level: info
      pipelines:
        traces:
          receivers: [otlp]
          processors: [memory_limiter, batch]
          exporters: [awsxray]
        metrics:
          receivers: [otlp]
          processors: [memory_limiter, batch]
          exporters: [awsemf]
  YAML
}

resource "aws_cloudwatch_dashboard" "operations" {
  dashboard_name = "${local.name_prefix}-operations"
  dashboard_body = jsonencode({
    widgets = [
      {
        type = "metric"
        width = 12
        height = 6
        properties = {
          title  = "ALB traffic, errors, and latency"
          region = var.aws_region
          view   = "timeSeries"
          stat   = "Sum"
          period = 300
          metrics = [
            ["AWS/ApplicationELB", "RequestCount", "LoadBalancer", aws_lb.backend.arn_suffix],
            [".", "HTTPCode_Target_4XX_Count", ".", "."],
            [".", "HTTPCode_Target_5XX_Count", ".", "."],
            [".", "TargetResponseTime", ".", ".", { stat = "Average" }],
          ]
        }
      },
      {
        type = "metric"
        width = 12
        height = 6
        properties = {
          title  = "ECS saturation"
          region = var.aws_region
          view   = "timeSeries"
          stat   = "Average"
          period = 300
          metrics = [
            ["AWS/ECS", "CPUUtilization", "ClusterName", aws_ecs_cluster.application.name, "ServiceName", aws_ecs_service.backend.name],
            [".", "MemoryUtilization", ".", ".", ".", "."],
          ]
        }
      },
      {
        type = "metric"
        width = 12
        height = 6
        properties = {
          title  = "RDS saturation and capacity"
          region = var.aws_region
          view   = "timeSeries"
          stat   = "Average"
          period = 300
          metrics = [
            ["AWS/RDS", "CPUUtilization", "DBInstanceIdentifier", aws_db_instance.application.identifier],
            [".", "DatabaseConnections", ".", "."],
            [".", "FreeStorageSpace", ".", "."],
          ]
        }
      },
      {
        type = "metric"
        width = 12
        height = 6
        properties = {
          title  = "Valkey saturation and connections"
          region = var.aws_region
          view   = "timeSeries"
          stat   = "Average"
          period = 300
          metrics = [
            ["AWS/ElastiCache", "EngineCPUUtilization", "CacheClusterId", aws_elasticache_replication_group.application.member_clusters[0]],
            [".", "DatabaseMemoryUsagePercentage", ".", "."],
            [".", "CurrConnections", ".", "."],
          ]
        }
      },
      {
        type = "metric"
        width = 24
        height = 6
        properties = {
          title  = "Application traffic, errors, and latency (when ADOT is enabled)"
          region = var.aws_region
          view   = "timeSeries"
          period = 300
          metrics = [
            [var.application_metric_namespace, "http.server.requests", { stat = "Sum" }],
            [".", "http.server.errors", { stat = "Sum" }],
            [".", "http.server.duration", { stat = "Average" }],
          ]
        }
      },
    ]
  })
}

resource "aws_sns_topic" "alarms" {
  count = var.enable_alarm_notifications ? 1 : 0

  name = "${local.name_prefix}-operational-alarms"
}

locals {
  alarm_actions = var.enable_alarm_notifications ? [aws_sns_topic.alarms[0].arn] : []
}

resource "aws_cloudwatch_metric_alarm" "alb_unhealthy_targets" {
  count = var.enable_operational_alarms ? 1 : 0

  alarm_name          = "${local.name_prefix}-alb-unhealthy-targets"
  alarm_description   = "Internal ALB has one or more unhealthy backend targets."
  namespace           = "AWS/ApplicationELB"
  metric_name         = "UnHealthyHostCount"
  statistic           = "Maximum"
  period              = 60
  evaluation_periods  = 2
  comparison_operator = "GreaterThanThreshold"
  threshold           = 0
  treat_missing_data  = "notBreaching"
  dimensions = {
    LoadBalancer = aws_lb.backend.arn_suffix
    TargetGroup  = aws_lb_target_group.backend.arn_suffix
  }
  alarm_actions = local.alarm_actions
}

resource "aws_cloudwatch_metric_alarm" "alb_backend_5xx" {
  count = var.enable_operational_alarms ? 1 : 0

  alarm_name          = "${local.name_prefix}-backend-5xx"
  alarm_description   = "Backend target 5xx responses exceed the initial operational threshold."
  namespace           = "AWS/ApplicationELB"
  metric_name         = "HTTPCode_Target_5XX_Count"
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  comparison_operator = "GreaterThanThreshold"
  threshold           = var.alarm_backend_5xx_count
  treat_missing_data  = "notBreaching"
  dimensions          = { LoadBalancer = aws_lb.backend.arn_suffix }
  alarm_actions       = local.alarm_actions
}

resource "aws_cloudwatch_metric_alarm" "ecs_cpu" {
  count = var.enable_operational_alarms ? 1 : 0

  alarm_name          = "${local.name_prefix}-ecs-high-cpu"
  namespace           = "AWS/ECS"
  metric_name         = "CPUUtilization"
  statistic           = "Average"
  period              = 300
  evaluation_periods  = 2
  comparison_operator = "GreaterThanThreshold"
  threshold           = var.alarm_cpu_threshold_percent
  treat_missing_data  = "notBreaching"
  dimensions = {
    ClusterName = aws_ecs_cluster.application.name
    ServiceName = aws_ecs_service.backend.name
  }
  alarm_actions = local.alarm_actions
}

resource "aws_cloudwatch_metric_alarm" "ecs_memory" {
  count = var.enable_operational_alarms ? 1 : 0

  alarm_name          = "${local.name_prefix}-ecs-high-memory"
  namespace           = "AWS/ECS"
  metric_name         = "MemoryUtilization"
  statistic           = "Average"
  period              = 300
  evaluation_periods  = 2
  comparison_operator = "GreaterThanThreshold"
  threshold           = var.alarm_memory_threshold_percent
  treat_missing_data  = "notBreaching"
  dimensions = {
    ClusterName = aws_ecs_cluster.application.name
    ServiceName = aws_ecs_service.backend.name
  }
  alarm_actions = local.alarm_actions
}

resource "aws_cloudwatch_metric_alarm" "rds_cpu" {
  count = var.enable_operational_alarms ? 1 : 0

  alarm_name          = "${local.name_prefix}-rds-high-cpu"
  namespace           = "AWS/RDS"
  metric_name         = "CPUUtilization"
  statistic           = "Average"
  period              = 300
  evaluation_periods  = 2
  comparison_operator = "GreaterThanThreshold"
  threshold           = var.alarm_cpu_threshold_percent
  treat_missing_data  = "notBreaching"
  dimensions          = { DBInstanceIdentifier = aws_db_instance.application.identifier }
  alarm_actions       = local.alarm_actions
}

resource "aws_cloudwatch_metric_alarm" "rds_free_storage" {
  count = var.enable_operational_alarms ? 1 : 0

  alarm_name          = "${local.name_prefix}-rds-low-storage"
  namespace           = "AWS/RDS"
  metric_name         = "FreeStorageSpace"
  statistic           = "Average"
  period              = 300
  evaluation_periods  = 2
  comparison_operator = "LessThanThreshold"
  threshold           = var.alarm_rds_free_storage_bytes
  treat_missing_data  = "notBreaching"
  dimensions          = { DBInstanceIdentifier = aws_db_instance.application.identifier }
  alarm_actions       = local.alarm_actions
}

resource "aws_cloudwatch_metric_alarm" "cache_cpu" {
  count = var.enable_operational_alarms ? 1 : 0

  alarm_name          = "${local.name_prefix}-cache-high-cpu"
  namespace           = "AWS/ElastiCache"
  metric_name         = "EngineCPUUtilization"
  statistic           = "Average"
  period              = 300
  evaluation_periods  = 2
  comparison_operator = "GreaterThanThreshold"
  threshold           = var.alarm_cpu_threshold_percent
  treat_missing_data  = "notBreaching"
  dimensions = {
    CacheClusterId = aws_elasticache_replication_group.application.member_clusters[0]
  }
  alarm_actions = local.alarm_actions
}

resource "aws_cloudwatch_metric_alarm" "cache_memory" {
  count = var.enable_operational_alarms ? 1 : 0

  alarm_name          = "${local.name_prefix}-cache-high-memory"
  namespace           = "AWS/ElastiCache"
  metric_name         = "DatabaseMemoryUsagePercentage"
  statistic           = "Average"
  period              = 300
  evaluation_periods  = 2
  comparison_operator = "GreaterThanThreshold"
  threshold           = var.alarm_memory_threshold_percent
  treat_missing_data  = "notBreaching"
  dimensions = {
    CacheClusterId = aws_elasticache_replication_group.application.member_clusters[0]
  }
  alarm_actions = local.alarm_actions
}
