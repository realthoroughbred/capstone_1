#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/lib-k8s.sh
require_demo_context "${1:?Usage: 10-admission-test.sh CONTEXT}"
mkdir -p evidence
"${k[@]}" apply -f policies/kyverno/restricted.yaml
"${k[@]}" wait --for=condition=Ready clusterpolicy/team4-restricted --timeout=120s
python3 scripts/test-admission.py "$context" | tee "evidence/admission-${context}.log"
