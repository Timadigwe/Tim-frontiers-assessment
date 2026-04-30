#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENVIRONMENT="${1:-dev}"
export AWS_REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-us-west-2}}"
REGION="$AWS_REGION"

if [[ -z "${TF_STATE_BUCKET:-}" && -n "${GITHUB_ACTIONS:-}" ]]; then
  _acct=$(aws sts get-caller-identity --query Account --output text 2>/dev/null || true)
  if [[ -n "${_acct:-}" && "${_acct}" != "None" ]]; then
    export TF_STATE_BUCKET="tim-frontiers-terraform-state-${_acct}"
  fi
fi

cd "$ROOT/terraform"
INIT_CMD=(terraform init -input=false)
if [[ -n "${TF_STATE_BUCKET:-}" ]]; then
  INIT_CMD+=(
    -backend-config="bucket=${TF_STATE_BUCKET}"
    -backend-config="key=tim-frontiers/${ENVIRONMENT}/terraform.tfstate"
    -backend-config="region=${TF_STATE_REGION:-${AWS_REGION}}"
    -backend-config="encrypt=true"
  )
elif [[ -n "${GITHUB_ACTIONS:-}" ]]; then
  echo "error: TF_STATE_BUCKET unset" >&2
  exit 1
else
  INIT_CMD+=(-backend=false)
fi
"${INIT_CMD[@]}"

FRONTEND_BUCKET="$(terraform output -raw s3_frontend_bucket 2>/dev/null || true)"
if [[ -n "$FRONTEND_BUCKET" ]]; then
  aws s3 rm "s3://${FRONTEND_BUCKET}" --recursive --region "$REGION" || true
fi

terraform destroy -auto-approve \
  -var="environment=${ENVIRONMENT}" \
  -var="aws_region=${REGION}" \
  -var="create_app_runner=true"
