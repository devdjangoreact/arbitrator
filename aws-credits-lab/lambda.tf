# Activity: "Create a web app using AWS Lambda"

data "aws_iam_policy_document" "lambda_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "lambda" {
  name               = "${local.name}-lambda"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy_attachment" "lambda_basic" {
  role       = aws_iam_role.lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_lambda_function" "web_app" {
  function_name = "${local.name}-web"
  role          = aws_iam_role.lambda.arn
  handler       = "index.handler"
  runtime       = "python3.12"
  timeout       = 10

  filename         = "${path.module}/lambda/web_app.zip"
  source_code_hash = filebase64sha256("${path.module}/lambda/web_app.zip")

  environment {
    variables = {
      APP_NAME = local.name
    }
  }

  tags = {
    Name = "${local.name}-web"
  }
}

resource "aws_lambda_function_url" "web_app" {
  function_name      = aws_lambda_function.web_app.function_name
  authorization_type = "NONE"

  cors {
    allow_origins = ["*"]
    allow_methods = ["GET"]
    allow_headers = ["*"]
  }
}
