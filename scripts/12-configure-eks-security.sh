#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/lib-k8s.sh
require_demo_context team4-eks
export ESO_ROLE_ARN="$(terraform -chdir=infra output -raw eso_role_arn)"
export KYVERNO_ROLE_ARN="$(terraform -chdir=infra output -raw kyverno_role_arn)"
export DEMO_SECRET_ARN="$(terraform -chdir=infra output -raw demo_secret_arn)"
export ECR_REPOSITORY_URL="$(terraform -chdir=infra output -raw repository_url)"
export AWS_REGION="${AWS_REGION:-ap-northeast-2}"
"${k[@]}" apply -f k8s/rbac.yaml
"${k[@]}" apply -k policies/network
"${k[@]}" -n kyverno annotate serviceaccount kyverno-admission-controller \
  "eks.amazonaws.com/role-arn=$KYVERNO_ROLE_ARN" --overwrite
"${k[@]}" -n kyverno rollout restart deployment/kyverno-admission-controller
"${k[@]}" -n kyverno rollout status deployment/kyverno-admission-controller --timeout=180s
"${k[@]}" apply -f policies/kyverno/restricted.yaml
python3 scripts/render-template.py policies/kyverno/ecr-signatures.yaml.template | "${k[@]}" apply -f -
python3 scripts/render-template.py k8s/eso/aws.yaml.template | "${k[@]}" apply -f -
echo 'Configured. Prepopulate dedicated test secret, then run 09-eso-test.sh team4-eks aws.'
