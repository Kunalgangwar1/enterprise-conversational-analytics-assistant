variable "aws_region" {
  description = "AWS region; choose one that supports CloudFront VPC origins."
  type        = string
  default     = "ap-south-1"
}

variable "project_name" {
  description = "Generic project identifier used for tags."
  type        = string
  default     = "enterprise-conversational-analytics"
}

variable "environment" {
  description = "Deployment environment name."
  type        = string
  default     = "dev"
}

variable "vpc_cidr" {
  description = "CIDR for the dedicated application VPC."
  type        = string
  default     = "10.42.0.0/16"
}

variable "ecs_egress_mode" {
  description = "cost_optimized uses public task subnets; private uses private subnets and one NAT gateway."
  type        = string
  default     = "cost_optimized"

  validation {
    condition     = contains(["cost_optimized", "private"], var.ecs_egress_mode)
    error_message = "ecs_egress_mode must be cost_optimized or private."
  }
}

variable "backend_ecr_repository_name" {
  description = "Backend ECR repository created by the bootstrap layer."
  type        = string
  default     = "enterprise-conversational-analytics-backend"
}

variable "backend_image_tag" {
  description = "Immutable sha-<full-git-sha> backend image tag."
  type        = string

  validation {
    condition     = can(regex("^sha-[0-9a-f]{40}$", var.backend_image_tag))
    error_message = "backend_image_tag must be sha- followed by the full 40-character Git SHA."
  }
}

variable "ecs_cpu" {
  description = "Fargate task CPU units."
  type        = number
  default     = 512
}

variable "ecs_memory" {
  description = "Fargate task memory in MiB."
  type        = number
  default     = 1024
}

variable "ecs_desired_count" {
  description = "Initial backend task count."
  type        = number
  default     = 1
}

variable "enable_ecs_autoscaling" {
  description = "Create bounded CPU and memory target-tracking policies for the backend service."
  type        = bool
  default     = false
}

variable "ecs_min_capacity" {
  description = "Minimum backend task count when autoscaling is enabled."
  type        = number
  default     = 1
  validation {
    condition     = var.ecs_min_capacity >= 1 && var.ecs_min_capacity <= 10
    error_message = "ecs_min_capacity must be between 1 and 10."
  }
}

variable "ecs_max_capacity" {
  description = "Maximum backend task count when autoscaling is enabled."
  type        = number
  default     = 3
  validation {
    condition     = var.ecs_max_capacity >= 1 && var.ecs_max_capacity <= 20
    error_message = "ecs_max_capacity must be between 1 and 20."
  }
}

variable "ecs_autoscaling_cpu_target" {
  description = "Target average ECS service CPU utilization."
  type        = number
  default     = 65
  validation {
    condition     = var.ecs_autoscaling_cpu_target >= 10 && var.ecs_autoscaling_cpu_target <= 90
    error_message = "ecs_autoscaling_cpu_target must be between 10 and 90."
  }
}

variable "ecs_autoscaling_memory_target" {
  description = "Target average ECS service memory utilization."
  type        = number
  default     = 70
  validation {
    condition     = var.ecs_autoscaling_memory_target >= 10 && var.ecs_autoscaling_memory_target <= 90
    error_message = "ecs_autoscaling_memory_target must be between 10 and 90."
  }
}

variable "ecs_scale_in_cooldown_seconds" {
  description = "Target-tracking scale-in cooldown."
  type        = number
  default     = 300
  validation {
    condition     = var.ecs_scale_in_cooldown_seconds >= 0 && var.ecs_scale_in_cooldown_seconds <= 3600
    error_message = "ecs_scale_in_cooldown_seconds must be between 0 and 3600."
  }
}

variable "ecs_scale_out_cooldown_seconds" {
  description = "Target-tracking scale-out cooldown."
  type        = number
  default     = 60
  validation {
    condition     = var.ecs_scale_out_cooldown_seconds >= 0 && var.ecs_scale_out_cooldown_seconds <= 3600
    error_message = "ecs_scale_out_cooldown_seconds must be between 0 and 3600."
  }
}

variable "backend_worker_processes" {
  description = "Uvicorn worker processes per ECS task."
  type        = number
  default     = 1
  validation {
    condition     = var.backend_worker_processes >= 1 && var.backend_worker_processes <= 8
    error_message = "backend_worker_processes must be between 1 and 8."
  }
}

variable "database_pool_size" {
  description = "Bounded SQLAlchemy pool size per worker and engine."
  type        = number
  default     = 5
  validation {
    condition     = var.database_pool_size >= 1 && var.database_pool_size <= 20
    error_message = "database_pool_size must be between 1 and 20."
  }
}

variable "database_max_overflow" {
  description = "Bounded SQLAlchemy overflow per worker and engine."
  type        = number
  default     = 5
  validation {
    condition     = var.database_max_overflow >= 0 && var.database_max_overflow <= 20
    error_message = "database_max_overflow must be between 0 and 20."
  }
}

variable "database_pool_recycle_seconds" {
  description = "Age at which pooled PostgreSQL connections are recycled."
  type        = number
  default     = 1800
  validation {
    condition     = var.database_pool_recycle_seconds >= 60 && var.database_pool_recycle_seconds <= 86400
    error_message = "database_pool_recycle_seconds must be between 60 and 86400."
  }
}

variable "database_pools_per_worker" {
  description = "Conservative pool multiplier covering application, dashboard, and SQL executors."
  type        = number
  default     = 3
  validation {
    condition     = var.database_pools_per_worker >= 1 && var.database_pools_per_worker <= 5
    error_message = "database_pools_per_worker must be between 1 and 5."
  }
}

variable "database_connection_budget" {
  description = "Maximum PostgreSQL connections allocated to backend application pools."
  type        = number
  default     = 100
  validation {
    condition     = var.database_connection_budget >= 10 && var.database_connection_budget <= 10000
    error_message = "database_connection_budget must be between 10 and 10000."
  }
}

variable "database_connection_reserve" {
  description = "Connections reserved for migrations, administration, and recovery."
  type        = number
  default     = 10
  validation {
    condition     = var.database_connection_reserve >= 0 && var.database_connection_reserve <= 1000
    error_message = "database_connection_reserve must be between 0 and 1000."
  }
}

variable "log_retention_days" {
  description = "CloudWatch container log retention."
  type        = number
  default     = 7
}

variable "observability_enabled" {
  description = "Run the ADOT sidecar and export application metrics/traces."
  type        = bool
  default     = false
}

variable "service_name" {
  description = "Low-cardinality OpenTelemetry service name."
  type        = string
  default     = "enterprise-conversational-analytics-backend"

  validation {
    condition     = can(regex("^[A-Za-z0-9._-]{1,128}$", var.service_name))
    error_message = "service_name must be a bounded low-cardinality identifier."
  }
}

variable "adot_collector_image" {
  description = "Explicitly versioned AWS-supported ADOT collector image."
  type        = string
  default     = "public.ecr.aws/aws-observability/aws-otel-collector:v0.49.0"

  validation {
    condition = can(regex(
      "^public\\.ecr\\.aws/aws-observability/aws-otel-collector:v[0-9]+\\.[0-9]+\\.[0-9]+$",
      var.adot_collector_image,
    ))
    error_message = "adot_collector_image must use an explicit semantic version, never latest."
  }
}

variable "application_metric_namespace" {
  description = "CloudWatch namespace for bounded application metrics exported by ADOT."
  type        = string
  default     = "EnterpriseConversationalAnalytics"
}

variable "otel_trace_sample_ratio" {
  description = "Head-sampling ratio for application traces."
  type        = number
  default     = 0.10

  validation {
    condition     = var.otel_trace_sample_ratio >= 0 && var.otel_trace_sample_ratio <= 1
    error_message = "otel_trace_sample_ratio must be between zero and one."
  }
}

variable "enable_container_insights" {
  description = "Enable basic ECS Container Insights; disabled by the cost-aware default."
  type        = bool
  default     = false
}

variable "enable_operational_alarms" {
  description = "Create the initial bounded set of CloudWatch operational alarms."
  type        = bool
  default     = false
}

variable "enable_alarm_notifications" {
  description = "Create an un-subscribed SNS topic and attach it to enabled alarms."
  type        = bool
  default     = false
}

variable "alarm_cpu_threshold_percent" {
  description = "Initial ECS/RDS/cache high-CPU threshold."
  type        = number
  default     = 80
}

variable "alarm_memory_threshold_percent" {
  description = "Initial ECS/cache high-memory threshold."
  type        = number
  default     = 80
}

variable "alarm_rds_free_storage_bytes" {
  description = "Initial RDS low-free-storage threshold in bytes."
  type        = number
  default     = 5368709120
}

variable "alarm_backend_5xx_count" {
  description = "Backend 5xx count in one five-minute evaluation period."
  type        = number
  default     = 5
}

variable "database_name" {
  description = "Application PostgreSQL database name."
  type        = string
  default     = "enterprise_analytics"
}

variable "database_engine_version" {
  description = "RDS PostgreSQL engine major version."
  type        = string
  default     = "16"
}

variable "database_parameter_group_family" {
  description = "RDS parameter group family matching the configured PostgreSQL major version."
  type        = string
  default     = "postgres16"
}

variable "database_instance_class" {
  description = "Cost-aware RDS instance class."
  type        = string
  default     = "db.t4g.micro"
}

variable "database_allocated_storage" {
  description = "Initial encrypted gp3 storage in GiB."
  type        = number
  default     = 20
}

variable "database_multi_az" {
  description = "Enable Multi-AZ RDS; false is the cost-aware development default."
  type        = bool
  default     = false
}

variable "database_deletion_protection" {
  description = "Protect RDS from deletion. Enable for production."
  type        = bool
  default     = false
}

variable "database_skip_final_snapshot" {
  description = "Skip final snapshot on destroy. Development default can cause data loss."
  type        = bool
  default     = true
}

variable "cache_engine_version" {
  description = "ElastiCache Valkey engine version."
  type        = string
  default     = "8.0"
}

variable "cache_node_type" {
  description = "Cost-aware ElastiCache node type."
  type        = string
  default     = "cache.t4g.micro"
}

variable "cognito_domain_prefix" {
  description = "Optional globally unique Cognito managed-login domain prefix."
  type        = string
  default     = null
  nullable    = true
}

variable "gemini_secret_arn" {
  description = "Optional existing Secrets Manager ARN whose value is a Gemini API key."
  type        = string
  default     = null
  nullable    = true
}

variable "gemini_secret_kms_key_arn" {
  description = "Optional customer-managed KMS key ARN used by the Gemini secret."
  type        = string
  default     = null
  nullable    = true
}

variable "application_secret_version" {
  description = "Increment deliberately to rotate generated database role credentials."
  type        = number
  default     = 1
}

variable "cache_secret_version" {
  description = "Increment deliberately to rotate the Valkey auth token."
  type        = number
  default     = 1
}

variable "secret_recovery_window_days" {
  description = "Secrets Manager recovery window."
  type        = number
  default     = 7
}

variable "frontend_force_destroy" {
  description = "Allow Terraform to delete a non-empty frontend bucket. Keep false for production."
  type        = bool
  default     = false
}
