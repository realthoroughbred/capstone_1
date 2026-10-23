#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
# Prefer the approved GitHub environment for keyless signing and deployment.
: "${EXPECTED_ACCOUNT_ID:?set the approved account ID}"
: "${COSIGN_IDENTITY:?set the trusted signing certificate identity}"
export AWS_REGION="$(terraform -chdir=infra output -raw region)"
export EKS_CLUSTER="$(terraform -chdir=infra output -raw cluster_name)"
export ECR_REPOSITORY="$(terraform -chdir=infra output -raw repository_url)"
bash scripts/image-security.sh
bash scripts/publish-signed-image.sh "${1:?unique immutable image tag}"
bash scripts/deploy-verified-image.sh
