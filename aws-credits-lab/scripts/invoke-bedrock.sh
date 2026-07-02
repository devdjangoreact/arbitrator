#!/usr/bin/env bash
set -euo pipefail

MODEL="${1:-sonnet}"
PROMPT="${2:-Say hello in one short sentence.}"
REGION="${3:-us-east-1}"

LAB_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$LAB_DIR"

# shellcheck source=bedrock-preflight.sh
source "$(dirname "$0")/bedrock-preflight.sh"

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

bedrock_preflight_checks "$MODEL" "$MODEL_ID" "$REGION"

BODY_FILE="$(mktemp)"
RESP_FILE="$(mktemp)"
trap 'rm -f "$BODY_FILE" "$RESP_FILE"' EXIT

printf '{"anthropic_version":"bedrock-2023-05-31","max_tokens":128,"messages":[{"role":"user","content":"%s"}]}' "$PROMPT" >"$BODY_FILE"

echo "Invoking model: $MODEL_ID in $REGION"
echo "Prompt: $PROMPT"
echo

set +e
invoke_output="$(aws bedrock-runtime invoke-model \
  --region "$REGION" \
  --model-id "$MODEL_ID" \
  --content-type application/json \
  --accept application/json \
  --body "fileb://$BODY_FILE" \
  "$RESP_FILE" 2>&1)"
invoke_status=$?
set -e

if [[ $invoke_status -ne 0 ]] || [[ ! -s "$RESP_FILE" ]]; then
  bedrock_access_denied_help "$MODEL" "$MODEL_ID" "$REGION" "$invoke_output"
  exit 1
fi

python -m json.tool "$RESP_FILE" 2>/dev/null || cat "$RESP_FILE"
