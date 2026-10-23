#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/lib-k8s.sh
require_demo_context "${1:?Usage: 11-gitops-drift-test.sh CONTEXT}"
: "${GITOPS_REPO_URL:?}" "${GITOPS_REVISION:?40-character published commit required}"
[[ "$GITOPS_REVISION" =~ ^[a-f0-9]{40}$ ]]
export GITOPS_REPO_URL GITOPS_REVISION
mkdir -p evidence
python3 scripts/render-template.py k8s/gitops/application.yaml.template | "${k[@]}" apply -f -
python3 scripts/test-gitops-drift.py "$context" "$GITOPS_REVISION" | tee "evidence/gitops-${context}.log"
# This invocation only observes connectivity; it never reapplies NetworkPolicies.
bash scripts/08-network-policy-test.sh "$context" --verify-only
