# Activity 1: Launch an instance using EC2 ($20)

data "aws_ami" "amazon_linux" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["al2023-ami-*-x86_64"]
  }

  filter {
    name   = "state"
    values = ["available"]
  }
}

resource "aws_security_group" "ec2" {
  name        = "${local.name}-ec2-sg"
  description = "Temporary SG for credits EC2 instance"
  vpc_id      = data.aws_vpc.default.id

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${local.name}-ec2" }
}

resource "aws_instance" "credits" {
  ami                    = data.aws_ami.amazon_linux.id
  instance_type          = "t3.micro"
  subnet_id              = data.aws_subnets.default.ids[0]
  vpc_security_group_ids = [aws_security_group.ec2.id]

  tags = { Name = "${local.name}-ec2" }
}

# Activity 2: Set up a cost budget using AWS Budgets ($20)

resource "aws_budgets_budget" "credits" {
  name         = "${local.name}-budget"
  budget_type  = "COST"
  limit_amount = var.budget_limit_usd
  limit_unit   = "USD"
  time_unit    = "MONTHLY"
}

# Activity 3: Create a web app using AWS Lambda ($20)

data "archive_file" "lambda" {
  type        = "zip"
  output_path = "${path.module}/lambda.zip"

  source {
    content  = <<-PY
      def handler(event, context):
          return {
              "statusCode": 200,
              "headers": {"Content-Type": "text/html"},
              "body": "<h1>Arbitrator AWS Credits Lab</h1>",
          }
    PY
    filename = "index.py"
  }
}

resource "aws_iam_role" "lambda" {
  name = "${local.name}-lambda-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "lambda_basic" {
  role       = aws_iam_role.lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_lambda_function" "credits" {
  function_name    = "${local.name}-web-app"
  role             = aws_iam_role.lambda.arn
  handler          = "index.handler"
  runtime          = "python3.13"
  filename         = data.archive_file.lambda.output_path
  source_code_hash = data.archive_file.lambda.output_base64sha256
  timeout          = 30

  tags = { Name = "${local.name}-lambda" }
}

resource "aws_lambda_function_url" "credits" {
  function_name      = aws_lambda_function.credits.function_name
  authorization_type = "NONE"
}

# Activity 4: Create an Aurora or RDS database ($20)

resource "random_password" "rds" {
  length           = 16
  special          = true
  override_special = "!#$%&*()-_=+[]{}<>:?"
}

resource "aws_db_subnet_group" "credits" {
  name       = "${local.name}-db-subnet-group"
  subnet_ids = data.aws_subnets.default.ids

  tags = { Name = "${local.name}-db" }
}

resource "aws_security_group" "rds" {
  name        = "${local.name}-rds-sg"
  description = "Temporary SG for credits RDS instance"
  vpc_id      = data.aws_vpc.default.id

  tags = { Name = "${local.name}-rds" }
}

resource "aws_db_instance" "credits" {
  identifier             = "${local.name}-db"
  engine                 = "mysql"
  engine_version         = "8.0"
  instance_class         = "db.t3.micro"
  allocated_storage      = 20
  db_name                = "credits"
  username               = "admin"
  password               = random_password.rds.result
  db_subnet_group_name   = aws_db_subnet_group.credits.name
  vpc_security_group_ids = [aws_security_group.rds.id]
  skip_final_snapshot    = true
  publicly_accessible    = false
  deletion_protection    = false

  tags = { Name = "${local.name}-db" }
}
