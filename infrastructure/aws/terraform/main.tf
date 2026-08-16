provider "aws" { region = var.aws_region }

locals { enabled = var.enable_cloud_spine ? 1 : 0; prefix = "${var.project_name}-${var.environment}" }

resource "aws_dynamodb_table" "director_witness" {
  count = local.enabled
  name = "${local.prefix}-director-witness"
  billing_mode = "PAY_PER_REQUEST"
  hash_key = "lease_key"
  attribute { name = "lease_key"; type = "S" }
  point_in_time_recovery { enabled = true }
  server_side_encryption { enabled = true }
}

resource "aws_sqs_queue" "durable_events" {
  count = local.enabled
  name = "${local.prefix}-durable-events"
  sqs_managed_sse_enabled = true
  message_retention_seconds = 1209600
}

resource "aws_s3_bucket" "recovery" { count = local.enabled; bucket_prefix = "${local.prefix}-recovery-" }
resource "aws_s3_bucket_public_access_block" "recovery" {
  count = local.enabled; bucket = aws_s3_bucket.recovery[0].id
  block_public_acls = true; block_public_policy = true; ignore_public_acls = true; restrict_public_buckets = true
}
resource "aws_s3_bucket_versioning" "recovery" { count = local.enabled; bucket = aws_s3_bucket.recovery[0].id; versioning_configuration { status = "Enabled" } }
resource "aws_s3_bucket_server_side_encryption_configuration" "recovery" {
  count = local.enabled; bucket = aws_s3_bucket.recovery[0].id
  rule { apply_server_side_encryption_by_default { sse_algorithm = "AES256" } }
}
resource "aws_s3_bucket_lifecycle_configuration" "recovery" {
  count = local.enabled; bucket = aws_s3_bucket.recovery[0].id
  rule { id = "retention"; status = "Enabled"; expiration { days = var.backup_retention_days } }
}

resource "aws_cloudwatch_log_group" "recovery" { count = local.enabled; name = "/${local.prefix}/recovery"; retention_in_days = 30 }

resource "aws_budgets_budget" "monthly" {
  count = local.enabled; name = "${local.prefix}-monthly"; budget_type = "COST"; limit_amount = tostring(var.monthly_budget_usd); limit_unit = "USD"; time_unit = "MONTHLY"
}

# Independent external circuit breaker. Deliberately disabled by default. AWS Budgets
# evaluates this outside the local Budget Governor and may attach a pre-reviewed restrictive
# IAM policy when actual monthly spend reaches 100% of the account budget.
resource "aws_budgets_budget_action" "monthly_guardrail" {
  count = local.enabled == 1 && var.enable_budget_circuit_breaker ? 1 : 0
  budget_name        = aws_budgets_budget.monthly[0].name
  action_type        = "APPLY_IAM_POLICY"
  approval_model     = "AUTOMATIC"
  notification_type  = "ACTUAL"
  execution_role_arn = var.budget_action_execution_role_arn

  action_threshold {
    action_threshold_type  = "PERCENTAGE"
    action_threshold_value = 100
  }

  definition {
    iam_action_definition {
      policy_arn = var.budget_guardrail_policy_arn
      roles      = var.budget_guardrail_target_roles
    }
  }

  subscriber {
    subscription_type = "EMAIL"
    address           = var.budget_action_subscriber_email
  }

  lifecycle {
    precondition {
      condition = var.budget_action_execution_role_arn != "" && var.budget_guardrail_policy_arn != "" && length(var.budget_guardrail_target_roles) > 0 && var.budget_action_subscriber_email != ""
      error_message = "Budget circuit breaker requires explicit reviewed role/policy/targets/subscriber configuration."
    }
  }
}
