variable "aws_region" {
  description = "AWS region for all resources"
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Prefix for temporary credit-lab resource names"
  type        = string
  default     = "arbitrator-credits"
}

variable "budget_limit_usd" {
  description = "Monthly cost budget limit (USD) for AWS Budgets activity"
  type        = string
  default     = "10"
}

variable "bedrock_sonnet_model" {
  description = "Bedrock inference profile for Claude Code Sonnet"
  type        = string
  default     = "us.anthropic.claude-sonnet-4-6"
}

variable "bedrock_haiku_model" {
  description = "Bedrock inference profile for Claude Code Haiku"
  type        = string
  default     = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
}

variable "bedrock_opus_model" {
  description = "Bedrock inference profile for Claude Code Opus"
  type        = string
  default     = "us.anthropic.claude-opus-4-6-v1"
}
