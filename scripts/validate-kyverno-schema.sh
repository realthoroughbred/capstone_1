#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/lib-k8s.sh
require_demo_context "${1:-kind-team4}"
mkdir -p evidence
exec > >(tee "evidence/kyverno-schema-${context}.log") 2>&1
# This dummy repository is only a policy string; no ECR image or AWS API is read.
export ECR_REPOSITORY_URL=123456789012.dkr.ecr.ap-northeast-2.amazonaws.com/team4-test
"${k[@]}" apply --dry-run=server --validate=strict -f policies/kyverno/restricted.yaml
python3 scripts/render-template.py policies/kyverno/ecr-signatures.yaml.template |
  "${k[@]}" apply --dry-run=server --validate=strict -f -
echo 'PASS: installed Kyverno CRD and admission accepted policy schema in server dry-run.'
echo 'NOT_TESTED: ECR authentication, signed image acceptance, and unsigned image rejection.'
