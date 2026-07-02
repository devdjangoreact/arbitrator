# AWS Credits Lab (Terraform)

Тимчасова інфраструктура для завершення активностей AWS Credits ($20 за кожну):

| Активність | Terraform-ресурс |
|---|---|
| Set up a cost budget using AWS Budgets | `aws_budgets_budget.monthly_cost` |
| Create a web app using AWS Lambda | `aws_lambda_function.web_app` + Function URL |
| Create an Aurora or RDS database | `aws_db_instance.lab` (MySQL db.t3.micro) |
| Use a foundation model in Amazon Bedrock | IAM + inference profiles + скрипт виклику |
| Launch an instance using EC2 | вже виконано в основному `terraform/` |

> **Увага:** Bedrock-активність потребує **одноразового** увімкнення моделей у консолі AWS (Terraform не може автоматично прийняти Anthropic use-case). Після цього достатньо одного виклику моделі через скрипт.

## Передумови

- [Terraform](https://developer.hashicorp.com/terraform/install) >= 1.11
- [AWS CLI](https://aws.amazon.com/cli/) v2
- AWS credentials з правами на Budgets, Lambda, RDS, Bedrock, IAM

## 1. Підготовка

```powershell
cd c:\shere-folder\arbitrator\aws-credits-lab

# Секрети: .env (credentials + пароль RDS)
Copy-Item .env.example .env
# Відредагуйте .env — AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_RDS_PASSWORD
# Пароль RDS: 8-41 символ, ASCII; заборонені / @ " і пробіл

# Завантажити .env у поточну сесію (credentials для AWS provider)
. .\scripts\load-env.ps1

# Необов'язково: terraform.tfvars для інших overrides
Copy-Item terraform.tfvars.example terraform.tfvars
```

Terraform читає пароль RDS напряму з `.env` (`AWS_RDS_PASSWORD`) — не потрібно дублювати його в `terraform.tfvars`.

## 2. Увімкнути доступ до моделей Bedrock (один раз)

> **Регіон:** увесь флоу — консоль, AWS CLI, Terraform provider, `invoke-bedrock` — має бути **`us-east-1` (N. Virginia)**. Не `eu-central-1` / Frankfurt: geo inference profiles для цих моделей тут не працюють.

1. Відкрийте [Amazon Bedrock Console](https://console.aws.amazon.com/bedrock/) з регіоном **US East (N. Virginia)** → **Model catalog** (сторінка Model access більше не використовується).
2. Для кожної моделі відкрийте картку і пройдіть **Submit use case** (перший Anthropic-виклик у акаунті):
   - **Claude Opus 4.8** — geo ID: `us.anthropic.claude-opus-4-8`
   - **Claude Sonnet 5** — geo ID: `us.anthropic.claude-sonnet-5`
   - **Claude Fable 5** — geo ID: `us.anthropic.claude-fable-5`
3. **Claude Fable 5 (Mythos-class):** окремо прийміть **30-day data retention** у Bedrock Console. Без цього Fable повертає `AccessDeniedException`, навіть якщо use-case form уже подана.
4. **Claude Fable 5** у Model catalog позначений як **RESTRICTED** — доступ може вимагати погодження з **AWS Sales** і не гарантується автоматично на trial/free tier акаунтах.

Без кроків 1–2 `invoke-bedrock` поверне `AccessDeniedException` з текстом *not available for this account*. Скрипт пояснить причину (use-case / Fable retention / IAM).

Перевірка регіону CLI:

```powershell
aws configure get region
$env:AWS_DEFAULT_REGION   # має бути us-east-1 або порожньо (тоді --region us-east-1 у скрипті)
```

## 3. Розгортання

> **Credentials для Terraform:** `terraform apply` запускайте під **основним admin-ключем** акаунту (Budgets, Lambda, RDS, IAM, EC2). Ключі `aws-credits-lab-bedrock` — лише для `invoke-bedrock.ps1`, не для Terraform. Якщо після invoke у сесії лишились bedrock keys — відкрийте новий термінал або очистіть `$env:AWS_ACCESS_KEY_ID` / `$env:AWS_SECRET_ACCESS_KEY`.

```powershell
aws sts get-caller-identity   # має бути ваш admin user/role, НЕ aws-credits-lab-bedrock

terraform init
terraform plan
terraform apply
```

Після `apply` збережіть outputs:

```powershell
terraform output
terraform output -raw lambda_function_url
terraform output -raw bedrock_access_key_id
terraform output -raw bedrock_secret_access_key   # sensitive — не комітьте
```

## 4. Перевірка активностей

### Budget
Перевірте в [AWS Budgets](https://console.aws.amazon.com/billing/home#/budgets) — бюджет `aws-credits-lab-monthly-cost`.

### Lambda web app
Відкрийте URL з output `lambda_function_url` у браузері — має з'явитися HTML-сторінка.

### RDS
Перевірте в [RDS Console](https://console.aws.amazon.com/rds/) — інстанс `aws-credits-lab-mysql` (статус `available`).

### Bedrock — виклик Opus 4.8, Sonnet 5 і Fable 5

```powershell
# Sonnet (дешевший для тесту)
.\scripts\invoke-bedrock.ps1 -Model sonnet -Prompt "Привіт! Відповідай українською."

# Opus 4.8
.\scripts\invoke-bedrock.ps1 -Model opus -Prompt "Say hello in one sentence."

# Fable 5
.\scripts\invoke-bedrock.ps1 -Model fable -Prompt "Say hello in one sentence."
```

Альтернатива через AWS CLI напряму (після `terraform apply`):

```powershell
$modelId = terraform output -raw bedrock_sonnet_model_id
$env:AWS_ACCESS_KEY_ID     = terraform output -raw bedrock_access_key_id
$env:AWS_SECRET_ACCESS_KEY = terraform output -raw bedrock_secret_access_key
$env:AWS_DEFAULT_REGION    = "us-east-1"

@'
{"anthropic_version":"bedrock-2023-05-31","max_tokens":128,"messages":[{"role":"user","content":"Hello"}]}
'@ | Set-Content request.json -Encoding utf8

aws bedrock-runtime invoke-model `
  --model-id $modelId `
  --content-type application/json `
  --accept application/json `
  --body file://request.json `
  response.json

Get-Content response.json
```

### Перевірка кредитів
Перевірте прогрес у AWS Credits / Skills Builder — активності можуть оновлюватися з затримкою до кількох годин.

## 5. Використання Bedrock у коді

Після `terraform apply` доступні:

| Output | Призначення |
|---|---|
| `bedrock_opus_model_id` | ID моделі Opus 4.8 |
| `bedrock_sonnet_model_id` | ID моделі Sonnet 5 |
| `bedrock_fable_model_id` | ID моделі Claude Fable 5 |
| `bedrock_opus_inference_profile_arn` | Inference profile для Opus (трекінг витрат) |
| `bedrock_sonnet_inference_profile_arn` | Inference profile для Sonnet 5 |
| `bedrock_fable_inference_profile_arn` | Inference profile для Fable 5 |
| `bedrock_runtime_endpoint` | Endpoint Bedrock Runtime API |
| `bedrock_access_key_id` / `bedrock_secret_access_key` | Окремий IAM user для API |

**Python (boto3):**

```python
import boto3, json

client = boto3.client("bedrock-runtime", region_name="us-east-1")
response = client.invoke_model(
    modelId="us.anthropic.claude-sonnet-5",
    body=json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 256,
        "messages": [{"role": "user", "content": "Hello"}],
    }),
)
print(json.loads(response["body"].read()))
```

**Converse API** (новіший інтерфейс):

```python
client.converse(
    modelId="us.anthropic.claude-fable-5",
    messages=[{"role": "user", "content": [{"text": "Hello"}]}],
)
```

## 6. Видалення всіх ресурсів

Після отримання кредитів:

```powershell
terraform destroy
```

Це видалить Budget, Lambda, RDS, IAM user/keys, Bedrock inference profiles. RDS видалиться без final snapshot (`skip_final_snapshot = true`).

Якщо `destroy` зависне на RDS — зачекайте 5–10 хв (MySQL instance class).

## 7. Claude Code extension (Cursor / VS Code + Bedrock)

Після `terraform apply` можна підключити розширення **Claude Code** до тих самих моделей через Amazon Bedrock (без Anthropic API key).

### Передумови

- Розширення [Claude Code](https://marketplace.visualstudio.com/items?itemName=anthropic.claude-code) у Cursor або VS Code (v2.1.94+)
- Кроки 2–3 виконані: моделі увімкнені в Bedrock, Terraform застосовано
- Для **Fable 5** додатково: у Bedrock Console прийміть **30-day data retention** для Mythos-class моделей (інакше Fable поверне помилку доступу)

### Швидке налаштування (рекомендовано)

**Credentials:** Claude Code бере AWS keys з системи (env / `~/.aws/credentials`). У settings **не потрібно** дублювати `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`, якщо вони вже налаштовані для Terraform.

```powershell
cd c:\shere-folder\arbitrator\aws-credits-lab

# Моделі Bedrock -> .claude/settings.local.json (без ключів)
.\scripts\setup-claude-code.ps1

# Або глобально: %USERPROFILE%\.claude\settings.json
.\scripts\setup-claude-code.ps1 -Target user

# Опційно: окремий bedrock IAM user з terraform (зазвичай не потрібно)
# .\scripts\setup-claude-code.ps1 -IncludeBedrockKeys

# Cursor / VS Code: без Anthropic login
Copy-Item .vscode\settings.json.example .vscode\settings.json
```

Перезавантажте вікно: `Ctrl+Shift+P` → **Developer: Reload Window**.

### Що обов'язково в settings

| Параметр | Навіщо |
|---|---|
| `CLAUDE_CODE_USE_BEDROCK=1` | маршрут через Bedrock, не Anthropic API |
| `AWS_REGION=us-east-1` | region моделей (обов'язково в settings) |
| `ANTHROPIC_DEFAULT_*_MODEL` | Opus / Sonnet / Fable geo IDs |
| `claudeCode.disableLoginPrompt` | у `.vscode/settings.json` — інакше просить Anthropic login |

**Не потрібно в settings**, якщо вже є в системі: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_PROFILE`.

### Як перевірити

1. Відкрийте панель **Claude Code** у Cursor.
2. У чаті: **`/status`** — має бути **Amazon Bedrock**, region `us-east-1`.
3. Надішліть короткий prompt (напр. «Привіт») — має прийти відповідь.
4. **`/model sonnet`** / **`/model opus`** / **`/model fable`** — перемикання моделей.
5. CLI-перевірка Bedrock (окремо від extension):

```powershell
.\scripts\invoke-bedrock.ps1 -Model sonnet -Prompt "Hello"
```

| Симптом | Що перевірити |
|---|---|
| Anthropic login | `claudeCode.disableLoginPrompt: true` + reload |
| `AccessDeniedException` | моделі увімкнені в Bedrock Console (крок 2) |
| Fable не працює | 30-day data retention для Mythos у Bedrock |
| Credentials | `aws sts get-caller-identity` у тій же сесії, звідки запускаєте Cursor |

## Орієнтовна вартість

- **Budget, Lambda URL** — практично безкоштовно
- **RDS db.t3.micro** — free tier (750 год/міс) або ~$0.02/год; **видаліть одразу після зарахування кредитів**
- **Bedrock** — оплата за токени; для тесту використовуйте Sonnet і короткі промпти (`max_tokens: 128`)

## Структура файлів

```text
aws-credits-lab/
  budget.tf          # AWS Budget
  lambda.tf          # Lambda + Function URL
  rds.tf             # RDS MySQL
  bedrock.tf         # IAM + inference profiles
  network.tf         # Default VPC / SG для RDS
  claude/
    settings.local.json.example
  .env.example
  .vscode/
    settings.json.example
  scripts/
    invoke-bedrock.ps1
    invoke-bedrock.sh
    load-env.ps1
    read-env.ps1
    setup-claude-code.ps1
  lambda/web_app/    # Код Lambda
  terraform.tfvars.example
```
