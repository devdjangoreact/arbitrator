output "budget_name" {
  description = "Created AWS Budget name."
  value       = aws_budgets_budget.monthly_cost.name
}

output "lambda_function_url" {
  description = "Public URL for the Lambda web app (open in browser to verify)."
  value       = aws_lambda_function_url.web_app.function_url
}

output "rds_endpoint" {
  description = "RDS MySQL endpoint (private; for activity completion only)."
  value       = aws_db_instance.lab.endpoint
}

output "rds_identifier" {
  description = "RDS instance identifier."
  value       = aws_db_instance.lab.identifier
}

output "bedrock_region" {
  description = "AWS region where Bedrock models are configured."
  value       = var.aws_region
}

output "bedrock_opus_model_id" {
  description = "Model ID for Claude Opus 4.8."
  value       = var.bedrock_opus_model_id
}

output "bedrock_sonnet_model_id" {
  description = "Model ID for Claude Sonnet 5."
  value       = var.bedrock_sonnet_model_id
}

output "bedrock_fable_model_id" {
  description = "Model ID for Claude Fable 5."
  value       = var.bedrock_fable_model_id
}

output "bedrock_opus_inference_profile_arn" {
  description = "Application inference profile ARN for Opus 4.8."
  value       = aws_bedrock_inference_profile.opus.arn
}

output "bedrock_sonnet_inference_profile_arn" {
  description = "Application inference profile ARN for Sonnet 5."
  value       = aws_bedrock_inference_profile.sonnet.arn
}

output "bedrock_fable_inference_profile_arn" {
  description = "Application inference profile ARN for Claude Fable 5."
  value       = aws_bedrock_inference_profile.fable.arn
}

output "bedrock_iam_user" {
  description = "IAM user for programmatic Bedrock access."
  value       = aws_iam_user.bedrock.name
}

output "bedrock_access_key_id" {
  description = "Access key ID for the Bedrock IAM user."
  value       = aws_iam_access_key.bedrock.id
}

output "bedrock_secret_access_key" {
  description = "Secret access key for the Bedrock IAM user (sensitive)."
  value       = aws_iam_access_key.bedrock.secret
  sensitive   = true
}

output "bedrock_runtime_endpoint" {
  description = "Bedrock Runtime API endpoint for this region."
  value       = "https://bedrock-runtime.${var.aws_region}.amazonaws.com"
}
