variable "enable_cloud_spine" { type = bool; default = false; description = "Fail-closed activation flag. False creates no Project Pipeline cloud-spine resources." }
variable "project_name" { type = string; default = "project-pipeline" }
variable "environment" { type = string; default = "recovery" }
variable "aws_region" { type = string; default = "us-east-1" }
variable "backup_retention_days" { type = number; default = 30 }
variable "monthly_budget_usd" { type = number; default = 25 }
variable "enable_budget_circuit_breaker" {
  type = bool
  default = false
  description = "Fail-closed. Enables an AWS Budgets action only after the operator provides a reviewed execution role, restrictive IAM policy, target roles, and subscriber email."
}
variable "budget_action_execution_role_arn" { type = string; default = "" }
variable "budget_guardrail_policy_arn" { type = string; default = "" }
variable "budget_guardrail_target_roles" { type = list(string); default = [] }
variable "budget_action_subscriber_email" { type = string; default = "" }
