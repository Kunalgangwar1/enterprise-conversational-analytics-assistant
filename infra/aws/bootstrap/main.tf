locals {
  github_repository_subject = coalesce(var.github_repository, "unconfigured/unconfigured")
}

resource "aws_s3_bucket" "terraform_state" {
  bucket = var.state_bucket_name

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_versioning" "terraform_state" {
  bucket = aws_s3_bucket.terraform_state.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "terraform_state" {
  bucket = aws_s3_bucket.terraform_state.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "terraform_state" {
  bucket = aws_s3_bucket.terraform_state.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_ecr_repository" "backend" {
  name                 = var.ecr_repository_name
  image_tag_mutability = "IMMUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "AES256"
  }
}

resource "aws_ecr_lifecycle_policy" "backend" {
  repository = aws_ecr_repository.backend.name
  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Retain a bounded set of immutable backend images"
      selection = {
        tagStatus     = "tagged"
        tagPrefixList = ["sha-"]
        countType     = "imageCountMoreThan"
        countNumber   = var.ecr_image_retention_count
      }
      action = { type = "expire" }
    }]
  })
}

resource "aws_iam_openid_connect_provider" "github" {
  count = var.enable_github_oidc ? 1 : 0

  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]
}

data "aws_iam_policy_document" "github_assume_role" {
  for_each = var.enable_github_oidc ? var.github_trusted_environments : toset([])

  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    effect  = "Allow"

    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github[0].arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values = [
        "repo:${local.github_repository_subject}:environment:${each.key}"
      ]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:ref"
      values   = [var.github_trusted_ref]
    }
  }
}

resource "aws_iam_role" "github_deploy" {
  for_each = var.enable_github_oidc ? var.github_trusted_environments : toset([])

  name               = "eca-${each.key}-github-deploy"
  assume_role_policy = data.aws_iam_policy_document.github_assume_role[each.key].json
  tags               = { Environment = each.key }

  lifecycle {
    precondition {
      condition = (
        var.github_repository != null && length(var.github_trusted_environments) > 0
      )
      error_message = "github_repository and at least one trusted environment are required when GitHub OIDC is enabled."
    }
  }
}

data "aws_iam_policy_document" "github_deploy" {
  for_each = var.enable_github_oidc ? var.github_trusted_environments : toset([])

  statement {
    sid = "TerraformState"
    actions = [
      "s3:GetBucketVersioning",
      "s3:GetBucketLocation",
      "s3:GetObject",
      "s3:ListBucket",
      "s3:PutObject",
      "s3:DeleteObject",
    ]
    resources = [
      aws_s3_bucket.terraform_state.arn,
      "${aws_s3_bucket.terraform_state.arn}/*",
    ]
  }

  statement {
    sid = "BackendImages"
    actions = [
      "ecr:BatchCheckLayerAvailability",
      "ecr:BatchGetImage",
      "ecr:CompleteLayerUpload",
      "ecr:DescribeImages",
      "ecr:GetDownloadUrlForLayer",
      "ecr:InitiateLayerUpload",
      "ecr:ListImages",
      "ecr:PutImage",
      "ecr:UploadLayerPart",
    ]
    resources = [aws_ecr_repository.backend.arn]
  }

  statement {
    sid       = "EcrLogin"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }

  statement {
    sid = "ProjectInfrastructure"
    actions = [
      "cloudfront:*",
      "cognito-idp:*",
      "ec2:AllocateAddress",
      "ec2:AssociateRouteTable",
      "ec2:AttachInternetGateway",
      "ec2:AuthorizeSecurityGroupEgress",
      "ec2:AuthorizeSecurityGroupIngress",
      "ec2:CreateInternetGateway",
      "ec2:CreateNatGateway",
      "ec2:CreateRoute",
      "ec2:CreateRouteTable",
      "ec2:CreateSecurityGroup",
      "ec2:CreateSubnet",
      "ec2:CreateTags",
      "ec2:CreateVpc",
      "ec2:DeleteInternetGateway",
      "ec2:DeleteNatGateway",
      "ec2:DeleteRoute",
      "ec2:DeleteRouteTable",
      "ec2:DeleteSecurityGroup",
      "ec2:DeleteSubnet",
      "ec2:DeleteVpc",
      "ec2:Describe*",
      "ec2:DetachInternetGateway",
      "ec2:DisassociateRouteTable",
      "ec2:ModifySubnetAttribute",
      "ec2:ModifyVpcAttribute",
      "ec2:ReleaseAddress",
      "ec2:RevokeSecurityGroupEgress",
      "ec2:RevokeSecurityGroupIngress",
      "elasticache:*",
      "elasticloadbalancing:*",
      "rds:*",
    ]
    resources = ["*"]
  }

  statement {
    sid = "ProjectRuntimeAndStorage"
    actions = [
      "ecs:*",
      "logs:*",
      "s3:CreateBucket",
      "s3:DeleteBucket",
      "s3:DeleteBucketPolicy",
      "s3:DeleteObject",
      "s3:GetBucket*",
      "s3:GetObject",
      "s3:ListBucket",
      "s3:PutBucket*",
      "s3:PutObject",
      "secretsmanager:CreateSecret",
      "secretsmanager:DeleteSecret",
      "secretsmanager:DescribeSecret",
      "secretsmanager:GetSecretValue",
      "secretsmanager:ListSecretVersionIds",
      "secretsmanager:PutSecretValue",
      "secretsmanager:TagResource",
      "secretsmanager:UntagResource",
      "secretsmanager:UpdateSecret",
    ]
    resources = ["*"]
  }

  statement {
    sid = "ProjectCloudWatchMutation"
    actions = [
      "cloudwatch:DeleteAlarms",
      "cloudwatch:DeleteDashboards",
      "cloudwatch:PutDashboard",
      "cloudwatch:PutMetricAlarm",
      "cloudwatch:TagResource",
      "cloudwatch:UntagResource",
    ]
    resources = [
      "arn:aws:cloudwatch:${var.aws_region}:${data.aws_caller_identity.current.account_id}:alarm:eca-${each.key}-*",
      "arn:aws:cloudwatch::${data.aws_caller_identity.current.account_id}:dashboard/eca-${each.key}-*",
    ]
  }

  statement {
    sid       = "ProjectCloudWatchRead"
    actions   = ["cloudwatch:DescribeAlarms", "cloudwatch:ListTagsForResource"]
    resources = ["*"]
  }

  statement {
    sid = "ProjectObservabilityConfiguration"
    actions = [
      "ssm:AddTagsToResource",
      "ssm:DeleteParameter",
      "ssm:GetParameter",
      "ssm:GetParameters",
      "ssm:ListTagsForResource",
      "ssm:PutParameter",
      "ssm:RemoveTagsFromResource",
    ]
    resources = [
      "arn:aws:ssm:${var.aws_region}:${data.aws_caller_identity.current.account_id}:parameter/eca-${each.key}/*",
    ]
  }

  statement {
    sid = "ProjectAlarmTopic"
    actions = [
      "sns:CreateTopic",
      "sns:DeleteTopic",
      "sns:GetTopicAttributes",
      "sns:ListTagsForResource",
      "sns:SetTopicAttributes",
      "sns:TagResource",
      "sns:UntagResource",
    ]
    resources = [
      "arn:aws:sns:${var.aws_region}:${data.aws_caller_identity.current.account_id}:eca-${each.key}-*",
    ]
  }

  statement {
    sid = "ProjectIam"
    actions = [
      "iam:AttachRolePolicy",
      "iam:CreatePolicy",
      "iam:CreateRole",
      "iam:DeletePolicy",
      "iam:DeleteRole",
      "iam:DeleteRolePolicy",
      "iam:DetachRolePolicy",
      "iam:GetPolicy",
      "iam:GetPolicyVersion",
      "iam:GetRole",
      "iam:GetRolePolicy",
      "iam:ListAttachedRolePolicies",
      "iam:ListInstanceProfilesForRole",
      "iam:ListPolicyVersions",
      "iam:ListRolePolicies",
      "iam:PassRole",
      "iam:PutRolePolicy",
      "iam:TagPolicy",
      "iam:TagRole",
      "iam:UntagPolicy",
      "iam:UntagRole",
      "iam:UpdateAssumeRolePolicy",
    ]
    resources = [
      "arn:aws:iam::${data.aws_caller_identity.current.account_id}:role/eca-${each.key}-*",
      "arn:aws:iam::${data.aws_caller_identity.current.account_id}:policy/eca-${each.key}-*",
    ]
  }

  statement {
    sid       = "ServiceLinkedRoles"
    actions   = ["iam:CreateServiceLinkedRole"]
    resources = ["*"]

    condition {
      test     = "StringEquals"
      variable = "iam:AWSServiceName"
      values = [
        "ecs.amazonaws.com",
        "elasticache.amazonaws.com",
        "elasticloadbalancing.amazonaws.com",
        "rds.amazonaws.com",
      ]
    }
  }
}

resource "aws_iam_role_policy" "github_deploy" {
  for_each = var.enable_github_oidc ? var.github_trusted_environments : toset([])

  name   = "eca-${each.key}-terraform-deploy"
  role   = aws_iam_role.github_deploy[each.key].id
  policy = data.aws_iam_policy_document.github_deploy[each.key].json
}
