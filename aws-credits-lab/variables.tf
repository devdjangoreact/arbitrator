variable "aws_region" {
  description = "AWS region for all lab resources. Bedrock Anthropic models are available in us-east-1."
  type        = string
  default     = "us-east-1"
}

variable "project_prefix" {
  description = "Prefix for resource names (keep short; used in IAM and RDS identifiers)."
  type        = string
  default     = "aws-credits-lab"
}

variable "monthly_budget_limit_usd" {
  description = "Monthly cost budget limit in USD for the AWS Budgets activity."
  type        = string
  default     = "5"
}

variable "db_username" {
  description = "Master username for the RDS instance."
  type        = string
  default     = "labadmin"
}

variable "bedrock_opus_model_id" {
  description = "Bedrock model ID for Claude Opus 4.8 (use geo ID in us-east-1)."
  type        = string
  default     = "us.anthropic.claude-opus-4-8"
}

variable "bedrock_sonnet_model_id" {
  description = "Bedrock model ID for Claude Sonnet 5 (use geo ID in us-east-1)."
  type        = string
  default     = "us.anthropic.claude-sonnet-5"
}

variable "bedrock_fable_model_id" {
  description = "Bedrock model ID for Claude Fable 5 (use geo ID in us-east-1)."
  type        = string
  default     = "us.anthropic.claude-fable-5"
}
