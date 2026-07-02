# Activity: "Use a foundation model in Amazon Bedrock"
# Terraform provisions IAM access and inference profiles; model access in the Bedrock
# console must be enabled once per account (see README).

locals {
  # Bedrock Anthropic frontier models for this lab are pinned to us-east-1 only.
  bedrock_region = "us-east-1"
}

data "aws_iam_policy_document" "bedrock_invoke" {
  statement {
    sid    = "InvokeLabModelsInUsEast1"
    effect = "Allow"
    actions = [
      "bedrock:InvokeModel",
      "bedrock:InvokeModelWithResponseStream",
      "bedrock:Converse",
      "bedrock:ConverseStream",
    ]
    resources = [
      "arn:aws:bedrock:${local.bedrock_region}::foundation-model/anthropic.claude-opus-4-8*",
      "arn:aws:bedrock:${local.bedrock_region}::foundation-model/anthropic.claude-sonnet-5*",
      "arn:aws:bedrock:${local.bedrock_region}::foundation-model/anthropic.claude-fable-5*",
      "arn:aws:bedrock:*:${local.account_id}:inference-profile/us.anthropic.claude-*",
      "arn:aws:bedrock:*:${local.account_id}:application-inference-profile/*",
    ]
  }

  statement {
    sid    = "InvokeCrossRegionFoundationModels"
    effect = "Allow"
    actions = [
      "bedrock:InvokeModel",
      "bedrock:InvokeModelWithResponseStream",
      "bedrock:Converse",
      "bedrock:ConverseStream",
    ]
    resources = [
      "arn:aws:bedrock:*::foundation-model/anthropic.claude-opus-4-8*",
      "arn:aws:bedrock:*::foundation-model/anthropic.claude-sonnet-5*",
      "arn:aws:bedrock:*::foundation-model/anthropic.claude-fable-5*",
      "arn:aws:bedrock:*::inference-profile/us.anthropic.claude-*",
    ]
  }

  statement {
    sid    = "ReadModelsAndProfiles"
    effect = "Allow"
    actions = [
      "bedrock:GetInferenceProfile",
      "bedrock:ListFoundationModels",
      "bedrock:GetFoundationModel",
    ]
    resources = [
      "arn:aws:bedrock:*:${local.account_id}:inference-profile/*",
      "arn:aws:bedrock:*:${local.account_id}:application-inference-profile/*",
      "arn:aws:bedrock:*::foundation-model/*",
      "arn:aws:bedrock:*::inference-profile/*",
    ]
  }

  statement {
    sid    = "ReadAccountBedrockSettings"
    effect = "Allow"
    actions = [
      "bedrock:GetAccountDataRetention",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_policy" "bedrock_invoke" {
  name        = "${local.name}-bedrock-invoke"
  description = "Allow invoking Bedrock lab models in us-east-1 (Invoke API + cross-region routing)"
  policy      = data.aws_iam_policy_document.bedrock_invoke.json
}

resource "aws_iam_user" "bedrock" {
  name = "${local.name}-bedrock"
  tags = {
    Name = "${local.name}-bedrock"
  }
}

resource "aws_iam_user_policy_attachment" "bedrock" {
  user       = aws_iam_user.bedrock.name
  policy_arn = aws_iam_policy.bedrock_invoke.arn
}

resource "aws_iam_access_key" "bedrock" {
  user = aws_iam_user.bedrock.name
}

resource "aws_bedrock_inference_profile" "opus" {
  name        = "${local.name}-opus-48"
  description = "Credits lab profile for Claude Opus 4.8"

  model_source {
    copy_from = local.bedrock_model_source_arn.opus
  }

  tags = {
    Name  = "${local.name}-opus-48"
    Model = var.bedrock_opus_model_id
  }
}

resource "aws_bedrock_inference_profile" "sonnet" {
  name        = "${local.name}-sonnet-5"
  description = "Credits lab profile for Claude Sonnet 5"

  model_source {
    copy_from = local.bedrock_model_source_arn.sonnet
  }

  tags = {
    Name  = "${local.name}-sonnet-5"
    Model = var.bedrock_sonnet_model_id
  }
}

resource "aws_bedrock_inference_profile" "fable" {
  name        = "${local.name}-fable-5"
  description = "Credits lab profile for Claude Fable 5"

  model_source {
    copy_from = local.bedrock_model_source_arn.fable
  }

  tags = {
    Name  = "${local.name}-fable-5"
    Model = var.bedrock_fable_model_id
  }
}
