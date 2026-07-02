#!/usr/bin/env bash
set -euo pipefail

MODEL="${1:-sonnet}"
PROMPT="${2:-Say hello in one short sentence.}"
REGION="${3:-us-east-1}"

LAB_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$LAB_DIR"

command -v aws >/dev/null || { echo "AWS CLI required"; exit 1; }
command -v terraform >/dev/null || { echo "Terraform required"; exit 1; }

export AWS_ACCESS_KEY_ID
export AWS_SECRET_ACCESS_KEY
export AWS_DEFAULT_REGION="$REGION"
unset AWS_SESSION_TOKEN

AWS_ACCESS_KEY_ID="$(terraform output -raw bedrock_access_key_id)"
AWS_SECRET_ACCESS_KEY="$(terraform output -raw bedrock_secret_access_key)"

case "$MODEL" in
  opus)  MODEL_ID="$(terraform output -raw bedrock_opus_model_id)" ;;
  fable) MODEL_ID="$(terraform output -raw bedrock_fable_model_id)" ;;
  *)     MODEL_ID="$(terraform output -raw bedrock_sonnet_model_id)" ;;
esac

BODY_FILE="$(mktemp)"
RESP_FILE="$(mktemp)"
trap 'rm -f "$BODY_FILE" "$RESP_FILE"' EXIT

cat >"$BODY_FILE" <<EOF
{"anthropic_version":"bedrock-2023-05-31","max_tokens":128,"messages":[{"role":"user","content":"${PROMPT}"}]}
EOF

echo "Invoking model: $MODEL_ID in $REGION"
aws bedrock-runtime invoke-model \
  --model-id "$MODEL_ID" \
  --content-type application/json \
  --accept application/json \
  --body "file://$BODY_FILE" \
  "$RESP_FILE"

cat "$RESP_FILE" | python -m json.tool 2>/dev/null || cat "$RESP_FILE"
