resource "aws_cognito_user_pool" "application" {
  name                     = "${local.name_prefix}-users"
  username_attributes      = ["email"]
  auto_verified_attributes = ["email"]

  account_recovery_setting {
    recovery_mechanism {
      name     = "verified_email"
      priority = 1
    }
  }

  password_policy {
    minimum_length                   = 12
    require_lowercase                = true
    require_numbers                  = true
    require_symbols                  = true
    require_uppercase                = true
    temporary_password_validity_days = 7
  }

  user_attribute_update_settings {
    attributes_require_verification_before_update = ["email"]
  }
}

resource "aws_cognito_user_group" "viewer" {
  name         = "viewer"
  user_pool_id = aws_cognito_user_pool.application.id
  description  = "Read and conversational access"
  precedence   = 30
}

resource "aws_cognito_user_group" "analyst" {
  name         = "analyst"
  user_pool_id = aws_cognito_user_pool.application.id
  description  = "Analytical and generated-query access"
  precedence   = 20
}

resource "aws_cognito_user_group" "admin" {
  name         = "admin"
  user_pool_id = aws_cognito_user_pool.application.id
  description  = "Administrative application access"
  precedence   = 10
}

resource "aws_cognito_user_pool_domain" "application" {
  domain       = local.cognito_domain
  user_pool_id = aws_cognito_user_pool.application.id
}

resource "aws_cognito_user_pool_client" "spa" {
  name         = "${local.name_prefix}-spa"
  user_pool_id = aws_cognito_user_pool.application.id

  generate_secret                        = false
  allowed_oauth_flows_user_pool_client   = true
  allowed_oauth_flows                    = ["code"]
  allowed_oauth_scopes                   = ["openid", "email", "profile"]
  supported_identity_providers           = ["COGNITO"]
  callback_urls                          = [local.cloudfront_url]
  logout_urls                            = [local.cloudfront_url]
  default_redirect_uri                   = local.cloudfront_url
  enable_token_revocation                = true
  prevent_user_existence_errors          = "ENABLED"
  access_token_validity                  = 60
  id_token_validity                      = 60
  refresh_token_validity                 = 1

  token_validity_units {
    access_token  = "minutes"
    id_token      = "minutes"
    refresh_token = "days"
  }
}
