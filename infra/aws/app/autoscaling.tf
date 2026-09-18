resource "aws_appautoscaling_target" "backend" {
  count = var.enable_ecs_autoscaling ? 1 : 0

  max_capacity       = var.ecs_max_capacity
  min_capacity       = var.ecs_min_capacity
  resource_id        = "service/${aws_ecs_cluster.application.name}/${aws_ecs_service.backend.name}"
  scalable_dimension = "ecs:service:DesiredCount"
  service_namespace  = "ecs"
}

resource "aws_appautoscaling_policy" "backend_cpu" {
  count = var.enable_ecs_autoscaling ? 1 : 0

  name               = "${local.name_prefix}-backend-cpu"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.backend[0].resource_id
  scalable_dimension = aws_appautoscaling_target.backend[0].scalable_dimension
  service_namespace  = aws_appautoscaling_target.backend[0].service_namespace

  target_tracking_scaling_policy_configuration {
    target_value       = var.ecs_autoscaling_cpu_target
    scale_in_cooldown  = var.ecs_scale_in_cooldown_seconds
    scale_out_cooldown = var.ecs_scale_out_cooldown_seconds
    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageCPUUtilization"
    }
  }
}

resource "aws_appautoscaling_policy" "backend_memory" {
  count = var.enable_ecs_autoscaling ? 1 : 0

  name               = "${local.name_prefix}-backend-memory"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.backend[0].resource_id
  scalable_dimension = aws_appautoscaling_target.backend[0].scalable_dimension
  service_namespace  = aws_appautoscaling_target.backend[0].service_namespace

  target_tracking_scaling_policy_configuration {
    target_value       = var.ecs_autoscaling_memory_target
    scale_in_cooldown  = var.ecs_scale_in_cooldown_seconds
    scale_out_cooldown = var.ecs_scale_out_cooldown_seconds
    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageMemoryUtilization"
    }
  }
}

check "ecs_capacity_order" {
  assert {
    condition     = var.ecs_min_capacity <= var.ecs_desired_count && var.ecs_desired_count <= var.ecs_max_capacity
    error_message = "ecs_desired_count must remain between ecs_min_capacity and ecs_max_capacity."
  }
}

check "database_connection_budget" {
  assert {
    condition = (
      (var.enable_ecs_autoscaling ? var.ecs_max_capacity : var.ecs_desired_count) *
      var.backend_worker_processes * var.database_pools_per_worker *
      (var.database_pool_size + var.database_max_overflow) + var.database_connection_reserve
    ) <= var.database_connection_budget
    error_message = "ECS maximum task/worker/pool demand plus reserve exceeds database_connection_budget."
  }
}
