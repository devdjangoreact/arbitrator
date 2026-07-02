# RDS password is read from aws-credits-lab/.env (AWS_RDS_PASSWORD).

data "external" "lab_env" {
  program = [
    "powershell",
    "-NoProfile",
    "-NonInteractive",
    "-ExecutionPolicy",
    "Bypass",
    "-File",
    "${path.module}/scripts/read-env.ps1",
  ]
}

check "db_password_length" {
  assert {
    condition = (
      length(local.db_password) >= 8 &&
      length(local.db_password) <= 41
    )
    error_message = "AWS_RDS_PASSWORD in .env must be 8-41 characters (RDS MySQL limit)."
  }
}

check "db_password_chars" {
  assert {
    condition = (
      can(regex("^[ -~]+$", local.db_password)) &&
      !can(regex("[/@\" ]", local.db_password))
    )
    error_message = "AWS_RDS_PASSWORD must be printable ASCII and must not contain /, @, \", or space."
  }
}
