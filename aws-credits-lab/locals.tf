data "aws_caller_identity" "current" {}

data "aws_availability_zones" "available" {
  state = "available"
}

locals {
  account_id   = data.aws_caller_identity.current.account_id
  name         = var.project_prefix
  db_password  = data.external.lab_env.result.AWS_RDS_PASSWORD

  # Opus 4.8 has no in-region foundation-model endpoint in us-east-1; use geo inference profiles.
  bedrock_model_source_arn = {
    opus   = "arn:aws:bedrock:${var.aws_region}::inference-profile/${var.bedrock_opus_model_id}"
    sonnet = "arn:aws:bedrock:${var.aws_region}::inference-profile/${var.bedrock_sonnet_model_id}"
    fable  = "arn:aws:bedrock:${var.aws_region}::inference-profile/${var.bedrock_fable_model_id}"
  }
}
