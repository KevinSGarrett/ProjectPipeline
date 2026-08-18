variable "enable_cloud_spine" {
  type        = bool
  default = false
  description = "Fail-closed activation flag. False creates no Project Pipeline cloud-spine resources."
}

variable "project_name" {
  type    = string
  default = "project-pipeline"
}

variable "environment" {
  type    = string
  default = "recovery"
}

variable "aws_region" {
  type    = string
  default = "us-east-1"

  validation {
    condition     = contains(["us-east-1", "us-east-2", "us-west-1", "us-west-2", "eu-west-1", "eu-central-1"], var.aws_region)
    error_message = "aws_region must be an approved recovery region."
  }
}

variable "aws_account_id" {
  type        = string
  default     = ""
  description = "Optional 12-digit account id used only after explicit activation. Empty means no live account is assumed."

  validation {
    condition     = var.aws_account_id == "" || can(regex("^\\d{12}$", var.aws_account_id))
    error_message = "aws_account_id must be empty or a 12-digit account id."
  }
}
variable "state_lock_table" {
  type        = string
  default     = ""
  description = "Optional explicit DynamoDB lock table name for S3 backend configuration."
}

variable "state_bucket" {
  type        = string
  default     = ""
  description = "Optional explicit S3 backend bucket name. Empty means no live backend target is assumed."
}

variable "state_key" {
  type        = string
  default     = ""
  description = "Optional explicit state object key for backend configuration."
}
variable "backup_retention_days" {
  type    = number
  default = 30
}

variable "monthly_budget_usd" {
  type    = number
  default = 25
}

variable "enable_budget_circuit_breaker" {
  type        = bool
  default = false
  description = "Fail-closed. Enables an AWS Budgets action only after the operator provides a reviewed execution role, restrictive IAM policy, target roles, and subscriber email."
}

variable "budget_action_execution_role_arn" {
  type    = string
  default = ""
}

variable "budget_guardrail_policy_arn" {
  type    = string
  default = ""
}

variable "budget_guardrail_target_roles" {
  type    = list(string)
  default = []
}

variable "budget_action_subscriber_email" {
  type    = string
  default = ""
}
