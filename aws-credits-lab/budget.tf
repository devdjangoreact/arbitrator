# Activity: "Set up a cost budget using AWS Budgets"

resource "aws_budgets_budget" "monthly_cost" {
  name         = "${local.name}-monthly-cost"
  budget_type  = "COST"
  limit_amount = var.monthly_budget_limit_usd
  limit_unit   = "USD"
  time_unit    = "MONTHLY"
}
