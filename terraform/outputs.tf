output "account_id" {
  value = data.aws_caller_identity.current.account_id
}

output "aws_region" {
  value = var.aws_region
}

output "ec2_instance_id" {
  description = "Activity: Launch EC2"
  value       = aws_instance.credits.id
}

output "budget_name" {
  description = "Activity: AWS Budgets"
  value       = aws_budgets_budget.credits.name
}

output "lambda_function_url" {
  description = "Activity: Lambda web app"
  value       = aws_lambda_function_url.credits.function_url
}

output "rds_endpoint" {
  description = "Activity: RDS database"
  value       = aws_db_instance.credits.endpoint
  sensitive   = true
}

output "rds_password" {
  description = "RDS admin password (terraform state only)"
  value       = random_password.rds.result
  sensitive   = true
}

output "bedrock_claude_code_user" {
  description = "IAM user for Claude Code Bedrock auth"
  value       = aws_iam_user.claude_code.name
}

output "bedrock_access_key_id" {
  description = "Access key for Claude Code (set AWS_ACCESS_KEY_ID)"
  value       = aws_iam_access_key.claude_code.id
  sensitive   = true
}

output "bedrock_secret_access_key" {
  description = "Secret key for Claude Code (set AWS_SECRET_ACCESS_KEY)"
  value       = aws_iam_access_key.claude_code.secret
  sensitive   = true
}

output "claude_code_env" {
  description = "Environment variables for Claude Code with Bedrock"
  value = {
    CLAUDE_CODE_USE_BEDROCK           = "1"
    AWS_REGION                        = var.aws_region
    AWS_ACCESS_KEY_ID                 = aws_iam_access_key.claude_code.id
    AWS_SECRET_ACCESS_KEY             = aws_iam_access_key.claude_code.secret
    ANTHROPIC_DEFAULT_SONNET_MODEL    = var.bedrock_sonnet_model
    ANTHROPIC_DEFAULT_HAIKU_MODEL     = var.bedrock_haiku_model
    ANTHROPIC_DEFAULT_OPUS_MODEL      = var.bedrock_opus_model
  }
  sensitive = true
}

output "bedrock_playground_url" {
  description = "Activity 5 ($20): submit one prompt here (console only)"
  value       = "https://${var.aws_region}.console.aws.amazon.com/bedrock/home?region=${var.aws_region}#/playground"
}

output "bedrock_test_command" {
  description = "CLI test after first-time model access form is submitted"
  value       = "aws bedrock-runtime converse --region ${var.aws_region} --model-id ${var.bedrock_haiku_model} --messages '[{\"role\":\"user\",\"content\":[{\"text\":\"Hello from Terraform\"}]}]' out.json"
}

output "destroy_hint" {
  value = "After credits are awarded: terraform destroy"
}
