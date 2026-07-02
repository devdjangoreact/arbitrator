data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

resource "aws_security_group" "rds" {
  name        = "${local.name}-rds"
  description = "Minimal SG for credits-lab RDS (no inbound from internet)"
  vpc_id      = data.aws_vpc.default.id

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${local.name}-rds"
  }
}

resource "aws_db_subnet_group" "lab" {
  name       = "${local.name}-db-subnets"
  subnet_ids = data.aws_subnets.default.ids

  tags = {
    Name = "${local.name}-db-subnets"
  }
}
