#!/usr/bin/env bash
# Shared Bedrock preflight + AccessDenied diagnostics for invoke-bedrock.sh
# (sourced — do not enable errexit here)

BEDROCK_LAB_REGION="us-east-1"

bedrock_preflight_header() {
  local model="$1"
  local model_id="$2"
  local region="$3"
  echo "Bedrock preflight | model=${model} id=${model_id} region=${region}"
  if [[ "$region" != "$BEDROCK_LAB_REGION" ]]; then
    echo
    echo "[region] Expected us-east-1 for this lab; you passed ${region}."
    echo "         Switch console/CLI/Terraform to US East (N. Virginia)."
  fi
}

bedrock_preflight_checks() {
  local model="$1"
  local model_id="$2"
  local region="$3"

  bedrock_preflight_header "$model" "$model_id" "$region"

  if ! identity="$(aws sts get-caller-identity --region "$region" 2>&1)"; then
    echo
    echo "[credentials] AWS credentials are missing or invalid."
    echo "$identity"
    return 0
  fi

  account_id="$(python -c 'import json,sys; print(json.load(sys.stdin)["Account"])' <<<"$identity")"
  echo "[credentials] caller account ${account_id}"

  if ! model_check="$(aws bedrock get-foundation-model --model-identifier "$model_id" --region "$region" 2>&1)"; then
    echo
    echo "[model catalog] Could not read foundation model metadata (may still be entitlement, not IAM):"
    echo "$model_check"
  else
    echo "[model catalog] foundation model metadata OK"
  fi

  if [[ "$model" == "fable" ]]; then
    if ! retention="$(aws bedrock get-account-data-retention --region "$region" 2>&1)"; then
      echo
      echo "[fable retention] Could not read account data retention setting:"
      echo "$retention"
      echo "                  Fable 5 requires 30-day provider data retention in Bedrock Console."
    else
      mode="$(python -c 'import json,sys; print(json.load(sys.stdin).get("mode",""))' <<<"$retention")"
      echo "[fable retention] mode=${mode}"
      if [[ "$mode" != "provider_data_share" ]]; then
        echo
        echo "[fable retention] Fable 5 needs provider_data_share (30-day retention)."
        echo "                  Accept it in Bedrock Console before invoking Fable."
      fi
    fi
  fi

  echo
}

bedrock_access_denied_help() {
  local model="$1"
  local model_id="$2"
  local region="$3"
  local error_text="$4"
  local lower
  lower="$(printf '%s' "$error_text" | tr '[:upper:]' '[:lower:]')"

  echo
  echo "=== Bedrock invoke failed ==="
  echo "$error_text"
  echo

  if [[ "$lower" == *"not available for this account"* ]] \
    || [[ "$lower" == *"contact aws sales"* ]] \
    || [[ "$lower" == *"model use case"* ]] \
    || [[ "$lower" == *"submit use case"* ]]; then
    echo "[likely cause: (a) use-case / account entitlement]"
    echo "  - Open Bedrock Model catalog in us-east-1 and submit Anthropic use case for ${model_id}."
    echo "  - Trial accounts may not get Sonnet 5 / Opus 4.8 immediately; check model card status."
    if [[ "$model" == "fable" ]]; then
      echo "  - Fable 5 is RESTRICTED; AWS Sales approval may be required."
    fi
  fi

  if [[ "$model" == "fable" ]] \
    && { [[ "$lower" == *"data retention"* ]] \
      || [[ "$lower" == *"provider_data_share"* ]] \
      || [[ "$lower" == *"mythos"* ]] \
      || [[ "$lower" == *"retention mode"* ]]; }; then
    echo "[likely cause: (b) Fable data retention not accepted]"
    echo "  - In Bedrock Console (us-east-1) accept 30-day data retention for Mythos-class models."
  fi

  if [[ "$lower" == *"not authorized to perform"* ]] \
    || [[ "$lower" == *"explicit deny"* ]] \
    || [[ "$lower" == *"with an explicit deny"* ]]; then
    echo "[likely cause: (c) IAM permissions]"
    echo "  - Re-run terraform apply to refresh bedrock IAM policy."
    echo "  - Ensure invoke uses credentials allowed by aws-credits-lab-bedrock user or equivalent policy."
  fi

  if [[ "$region" != "$BEDROCK_LAB_REGION" ]]; then
    echo "[also check] Region mismatch: lab expects us-east-1, you used ${region}."
  fi

  echo
  echo "Terraform cannot automate use-case forms, Fable RESTRICTED approval, or data retention opt-in."
  echo "See README section 2 for manual console steps."
  echo
}
