resource "aws_db_subnet_group" "application" {
  name       = "${local.name_prefix}-database"
  subnet_ids = values(aws_subnet.private_data)[*].id
  tags       = { Name = "${local.name_prefix}-database" }
}

resource "aws_db_parameter_group" "application" {
  name   = "${local.name_prefix}-postgres"
  family = var.database_parameter_group_family

  parameter {
    name         = "rds.force_ssl"
    value        = "1"
    apply_method = "pending-reboot"
  }
}

resource "aws_db_instance" "application" {
  identifier = "${local.name_prefix}-postgres"

  engine                       = "postgres"
  engine_version               = var.database_engine_version
  instance_class               = var.database_instance_class
  allocated_storage            = var.database_allocated_storage
  max_allocated_storage        = max(var.database_allocated_storage * 2, 100)
  storage_type                 = "gp3"
  storage_encrypted            = true
  db_name                      = var.database_name
  username                     = "eca_admin"
  manage_master_user_password  = true
  port                         = local.database_port
  publicly_accessible          = false
  multi_az                     = var.database_multi_az
  db_subnet_group_name         = aws_db_subnet_group.application.name
  vpc_security_group_ids       = [aws_security_group.database.id]
  parameter_group_name         = aws_db_parameter_group.application.name
  backup_retention_period      = 1
  auto_minor_version_upgrade   = true
  deletion_protection          = var.database_deletion_protection
  skip_final_snapshot          = var.database_skip_final_snapshot
  final_snapshot_identifier    = var.database_skip_final_snapshot ? null : "${local.name_prefix}-postgres-final"
  copy_tags_to_snapshot        = true
  performance_insights_enabled = false
}

ephemeral "random_password" "application_database" {
  length  = 40
  special = false
}

ephemeral "random_password" "reader_database" {
  length  = 40
  special = false
}

resource "aws_secretsmanager_secret" "application_database" {
  name                    = "${local.name_prefix}/database/application"
  description             = "Runtime eca_app and SELECT-only eca_reader connection material"
  recovery_window_in_days = var.secret_recovery_window_days
}

resource "aws_secretsmanager_secret_version" "application_database" {
  secret_id = aws_secretsmanager_secret.application_database.id
  secret_string_wo = jsonencode({
    app_username    = "eca_app"
    app_password    = ephemeral.random_password.application_database.result
    reader_username = "eca_reader"
    reader_password = ephemeral.random_password.reader_database.result
    database_url = join("", [
      "postgresql+psycopg://eca_app:",
      urlencode(ephemeral.random_password.application_database.result),
      "@${aws_db_instance.application.address}:${local.database_port}/${var.database_name}",
      "?sslmode=verify-full&sslrootcert=${urlencode(local.rds_ca_bundle)}",
    ])
    query_database_url = join("", [
      "postgresql+psycopg://eca_reader:",
      urlencode(ephemeral.random_password.reader_database.result),
      "@${aws_db_instance.application.address}:${local.database_port}/${var.database_name}",
      "?sslmode=verify-full&sslrootcert=${urlencode(local.rds_ca_bundle)}",
    ])
  })
  secret_string_wo_version = var.application_secret_version
}
