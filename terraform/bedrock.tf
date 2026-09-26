# Bedrock IAM for Claude Code (Activity 5 + LLM access)

resource "aws_iam_policy" "claude_code_bedrock" {
  name        = "${local.name}-claude-code-bedrock"
  description = "Invoke Anthropic models on Bedrock for Claude Code"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "InvokeClaudeModels"
        Effect = "Allow"
        Action = [
          "bedrock:InvokeModel",
          "bedrock:InvokeModelWithResponseStream",
          "bedrock:ListInferenceProfiles",
          "bedrock:GetInferenceProfile",
          "bedrock:ListFoundationModels",
          "bedrock:GetFoundationModel",
        ]
        Resource = [
          "arn:aws:bedrock:*::foundation-model/anthropic.*",
          "arn:aws:bedrock:*:*:inference-profile/*",
          "arn:aws:bedrock:*:*:application-inference-profile/*",
        ]
      },
      {
        Sid    = "MarketplaceForBedrock"
        Effect = "Allow"
        Action = [
          "aws-marketplace:ViewSubscriptions",
          "aws-marketplace:Subscribe",
          "aws-marketplace:Unsubscribe",
        ]
        Resource = "*"
        Condition = {
          StringEquals = {
            "aws:CalledViaLast" = "bedrock.amazonaws.com"
          }
        }
      },
      {
        Sid      = "ModelAccessForm"
        Effect   = "Allow"
        Action   = ["bedrock:PutUseCaseForModelAccess", "bedrock:GetUseCaseForModelAccess"]
        Resource = "*"
      },
    ]
  })
}

resource "aws_iam_user" "claude_code" {
  name = "${local.name}-claude-code"
  path = "/"
}

resource "aws_iam_user_policy_attachment" "claude_code_bedrock" {
  user       = aws_iam_user.claude_code.name
  policy_arn = aws_iam_policy.claude_code_bedrock.arn
}

resource "aws_iam_access_key" "claude_code" {
  user = aws_iam_user.claude_code.name
}
