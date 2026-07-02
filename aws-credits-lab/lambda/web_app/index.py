import json
import os


def handler(event, context):
    app_name = os.environ.get("APP_NAME", "aws-credits-lab")
    html = f"""<!DOCTYPE html>
<html lang="uk">
<head>
  <meta charset="utf-8" />
  <title>{app_name}</title>
</head>
<body>
  <h1>AWS Credits Lab — Lambda Web App</h1>
  <p>Цей endpoint створено Terraform для активності AWS Credits.</p>
</body>
</html>"""
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "text/html; charset=utf-8"},
        "body": html,
    }
