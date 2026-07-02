# Activity: "Create an Aurora or RDS database"

resource "aws_db_instance" "lab" {
  identifier     = "${local.name}-mysql"
  engine         = "mysql"
  engine_version = "8.0"
  instance_class = "db.t3.micro"

  allocated_storage     = 20
  max_allocated_storage = 20
  storage_type          = "gp2"

  db_name  = "labdb"
  username = var.db_username
  password = local.db_password

  db_subnet_group_name   = aws_db_subnet_group.lab.name
  vpc_security_group_ids = [aws_security_group.rds.id]
  publicly_accessible    = false
  skip_final_snapshot    = true
  deletion_protection    = false

  backup_retention_period = 0
  apply_immediately       = true

  tags = {
    Name = "${local.name}-mysql"
  }
}
