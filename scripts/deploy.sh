#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export ENV="${1:-dev}"
export AWS_REGION="${DEFAULT_AWS_REGION:-${AWS_REGION:-us-west-2}}"

if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env"
  set +a
fi

if [[ -n "${OPENROUTER_API_KEY:-}" && -z "${TF_VAR_openrouter_api_key:-}" ]]; then
  export TF_VAR_openrouter_api_key="$OPENROUTER_API_KEY"
fi
if [[ -n "${OPENROUTER_MODEL:-}" && -z "${TF_VAR_openrouter_model:-}" ]]; then
  export TF_VAR_openrouter_model="$OPENROUTER_MODEL"
fi
if [[ -n "${MCP_SERVER_URL:-}" && -z "${TF_VAR_mcp_server_url:-}" ]]; then
  export TF_VAR_mcp_server_url="$MCP_SERVER_URL"
fi
if [[ -n "${OPENAI_API_KEY:-}" && -z "${TF_VAR_openai_api_key:-}" ]]; then
  export TF_VAR_openai_api_key="$OPENAI_API_KEY"
fi

if [[ -z "${TF_STATE_BUCKET:-}" && -n "${GITHUB_ACTIONS:-}" ]]; then
  _acct=$(aws sts get-caller-identity --query Account --output text 2>/dev/null || true)
  if [[ -n "${_acct:-}" && "${_acct}" != "None" ]]; then
    export TF_STATE_BUCKET="tim-frontiers-terraform-state-${_acct}"
  fi
fi

STATE_KEY="tim-frontiers/${ENV}/terraform.tfstate"
cd "$ROOT/terraform"
INIT_CMD=(terraform init -input=false)
if [[ -n "${TF_STATE_BUCKET:-}" ]]; then
  INIT_CMD+=(
    -backend-config="bucket=${TF_STATE_BUCKET}"
    -backend-config="key=${STATE_KEY}"
    -backend-config="region=${TF_STATE_REGION:-${AWS_REGION}}"
    -backend-config="encrypt=true"
  )
elif [[ -n "${GITHUB_ACTIONS:-}" ]]; then
  echo "error: TF_STATE_BUCKET unset in GitHub Actions" >&2
  exit 1
else
  INIT_CMD+=(-backend=false)
fi
"${INIT_CMD[@]}"

apprunner_in_state() {
  terraform state list 2>/dev/null | grep -q 'aws_apprunner_service.api'
}

RUN_FULL_APPLY_AFTER_IMAGE=false
if [[ "${SKIP_TERRAFORM:-0}" != "1" ]]; then
  if apprunner_in_state; then
    terraform apply -auto-approve \
      -var="environment=$ENV" \
      -var="aws_region=$AWS_REGION" \
      -var="create_app_runner=true"
  else
    terraform apply -auto-approve \
      -var="environment=$ENV" \
      -var="aws_region=$AWS_REGION" \
      -target=aws_ecr_repository.api \
      -target=aws_iam_role.app_runner_role \
      -target=aws_iam_role_policy_attachment.app_runner_ecr_access \
      -target=aws_iam_role.app_runner_instance_role \
      -target=aws_s3_bucket.frontend \
      -target=aws_s3_bucket_public_access_block.frontend \
      -target=aws_s3_bucket_ownership_controls.frontend \
      -target=aws_s3_bucket_website_configuration.frontend \
      -target=aws_s3_bucket_policy.frontend
    RUN_FULL_APPLY_AFTER_IMAGE=true
  fi
fi

ECR_URL=$(terraform output -raw ecr_repository_url)
BUCKET=$(terraform output -raw s3_frontend_bucket)
REGION="$AWS_REGION"
cd "$ROOT"
ECR_HOST="${ECR_URL%%/*}"
aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "$ECR_HOST"
docker buildx build --platform linux/amd64 \
  -f backend/Dockerfile \
  -t "${ECR_URL}:latest" \
  --push \
  .

if [[ "${SKIP_TERRAFORM:-0}" != "1" && "$RUN_FULL_APPLY_AFTER_IMAGE" == true ]]; then
  cd "$ROOT/terraform"
  terraform apply -auto-approve \
    -var="environment=$ENV" \
    -var="aws_region=$AWS_REGION" \
    -var="create_app_runner=true"
  cd "$ROOT"
fi

cd "$ROOT/terraform"
API_HTTPS=$(terraform output -raw app_runner_service_url)
SVC_ARN=$(terraform output -raw app_runner_service_arn)
cd "$ROOT"

if [[ -z "$API_HTTPS" || -z "$SVC_ARN" ]]; then
  echo "app_runner URL or ARN empty" >&2
  exit 1
fi
aws apprunner start-deployment --region "$REGION" --service-arn "$SVC_ARN" 2>/dev/null || true

cd "$ROOT/frontend"
export NEXT_PUBLIC_API_URL="${API_HTTPS}"
npm ci
npm run build
aws s3 sync out/ "s3://${BUCKET}/" --delete --region "$REGION"

FRONTEND_HTTP=$(cd "$ROOT/terraform" && terraform output -raw s3_frontend_website_url)
echo "Frontend: $FRONTEND_HTTP"
echo "API: $API_HTTPS"
