data "aws_iam_policy_document" "ecs_tasks_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "task_execution" {
  name               = "${local.name_prefix}-task-execution"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume_role.json
}

resource "aws_iam_role_policy_attachment" "task_execution" {
  role       = aws_iam_role.task_execution.name
  policy_arn = "arn:${data.aws_partition.current.partition}:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

data "aws_iam_policy_document" "task_execution_secrets" {
  statement {
    sid     = "RuntimeSecrets"
    actions = ["secretsmanager:GetSecretValue"]
    resources = compact([
      aws_secretsmanager_secret.application_database.arn,
      aws_secretsmanager_secret.cache.arn,
      aws_db_instance.application.master_user_secret[0].secret_arn,
      var.gemini_secret_arn,
    ])
  }

  dynamic "statement" {
    for_each = var.observability_enabled ? [1] : []
    content {
      sid       = "AdotConfiguration"
      actions   = ["ssm:GetParameter", "ssm:GetParameters"]
      resources = [aws_ssm_parameter.adot_config[0].arn]
    }
  }

  dynamic "statement" {
    for_each = var.gemini_secret_kms_key_arn == null ? [] : [var.gemini_secret_kms_key_arn]
    content {
      sid       = "GeminiSecretKey"
      actions   = ["kms:Decrypt"]
      resources = [statement.value]
    }
  }
}

resource "aws_iam_role_policy" "task_execution_secrets" {
  name   = "${local.name_prefix}-runtime-secrets"
  role   = aws_iam_role.task_execution.id
  policy = data.aws_iam_policy_document.task_execution_secrets.json
}

resource "aws_iam_role" "task" {
  name               = "${local.name_prefix}-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume_role.json
  description        = "Application task role; only optional ADOT export permissions"
}

data "aws_iam_policy_document" "task_observability" {
  count = var.observability_enabled ? 1 : 0

  statement {
    sid = "XRayExport"
    actions = [
      "xray:PutTelemetryRecords",
      "xray:PutTraceSegments",
    ]
    resources = ["*"]
  }

  statement {
    sid = "EmbeddedMetricFormatLogs"
    actions = [
      "logs:CreateLogStream",
      "logs:DescribeLogStreams",
      "logs:PutLogEvents",
    ]
    resources = [
      aws_cloudwatch_log_group.application_metrics[0].arn,
      "${aws_cloudwatch_log_group.application_metrics[0].arn}:*",
    ]
  }
}

resource "aws_iam_role_policy" "task_observability" {
  count = var.observability_enabled ? 1 : 0

  name   = "${local.name_prefix}-adot-export"
  role   = aws_iam_role.task.id
  policy = data.aws_iam_policy_document.task_observability[0].json
}
