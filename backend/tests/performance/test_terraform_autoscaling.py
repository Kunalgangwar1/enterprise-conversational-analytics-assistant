from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_autoscaling_is_optional_bounded_and_tracks_cpu_and_memory() -> None:
    variables = (ROOT / "infra/aws/app/variables.tf").read_text(encoding="utf-8")
    autoscaling = (ROOT / "infra/aws/app/autoscaling.tf").read_text(encoding="utf-8")

    assert 'variable "enable_ecs_autoscaling"' in variables
    assert "default     = false" in variables
    assert "var.ecs_max_capacity <= 20" in variables
    assert 'predefined_metric_type = "ECSServiceAverageCPUUtilization"' in autoscaling
    assert 'predefined_metric_type = "ECSServiceAverageMemoryUtilization"' in autoscaling
    assert 'check "database_connection_budget"' in autoscaling
    assert "database_connection_reserve" in autoscaling
