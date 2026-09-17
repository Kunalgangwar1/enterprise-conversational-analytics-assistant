data "aws_ec2_managed_prefix_list" "cloudfront_origin" {
  name = "com.amazonaws.global.cloudfront.origin-facing"
}

resource "aws_security_group" "alb" {
  name        = "${local.name_prefix}-alb"
  description = "CloudFront VPC-origin traffic only"
  vpc_id      = aws_vpc.application.id
  tags        = { Name = "${local.name_prefix}-alb" }
}

resource "aws_vpc_security_group_ingress_rule" "alb_from_cloudfront" {
  security_group_id = aws_security_group.alb.id
  prefix_list_id    = data.aws_ec2_managed_prefix_list.cloudfront_origin.id
  from_port         = 80
  to_port           = 80
  ip_protocol       = "tcp"
  description       = "HTTP from the AWS-managed CloudFront origin-facing prefix list"
}

resource "aws_security_group" "backend" {
  name        = "${local.name_prefix}-backend"
  description = "Backend tasks; ingress only from the internal ALB"
  vpc_id      = aws_vpc.application.id
  tags        = { Name = "${local.name_prefix}-backend" }
}

resource "aws_vpc_security_group_ingress_rule" "backend_from_alb" {
  security_group_id            = aws_security_group.backend.id
  referenced_security_group_id = aws_security_group.alb.id
  from_port                    = local.backend_port
  to_port                      = local.backend_port
  ip_protocol                  = "tcp"
}

resource "aws_vpc_security_group_egress_rule" "alb_to_backend" {
  security_group_id            = aws_security_group.alb.id
  referenced_security_group_id = aws_security_group.backend.id
  from_port                    = local.backend_port
  to_port                      = local.backend_port
  ip_protocol                  = "tcp"
}

resource "aws_vpc_security_group_egress_rule" "backend_outbound" {
  security_group_id = aws_security_group.backend.id
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "-1"
  description       = "TLS egress for AWS APIs and the configured external LLM provider"
}

resource "aws_security_group" "database" {
  name        = "${local.name_prefix}-database"
  description = "PostgreSQL only from backend tasks"
  vpc_id      = aws_vpc.application.id
  tags        = { Name = "${local.name_prefix}-database" }
}

resource "aws_vpc_security_group_ingress_rule" "database_from_backend" {
  security_group_id            = aws_security_group.database.id
  referenced_security_group_id = aws_security_group.backend.id
  from_port                    = local.database_port
  to_port                      = local.database_port
  ip_protocol                  = "tcp"
}

resource "aws_security_group" "cache" {
  name        = "${local.name_prefix}-cache"
  description = "TLS Valkey only from backend tasks"
  vpc_id      = aws_vpc.application.id
  tags        = { Name = "${local.name_prefix}-cache" }
}

resource "aws_vpc_security_group_ingress_rule" "cache_from_backend" {
  security_group_id            = aws_security_group.cache.id
  referenced_security_group_id = aws_security_group.backend.id
  from_port                    = local.cache_port
  to_port                      = local.cache_port
  ip_protocol                  = "tcp"
}
