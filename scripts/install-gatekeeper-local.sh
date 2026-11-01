#!/usr/bin/env bash
# Explicitly local: never use the active kube context (which may be EKS).
set -euo pipefail
cd "$(dirname "$0")/.."
context=kind-team4
server="$(kubectl --context "$context" config view --minify -o jsonpath='{.clusters[0].cluster.server}')"
case "$server" in https://127.0.0.1:*|https://localhost:*|https://\[::1\]:*) ;; *) echo 'Expected a local kind API endpoint' >&2; exit 1 ;; esac
out="${GATEKEEPER_EVIDENCE_DIR:?Set a fresh GATEKEEPER_EVIDENCE_DIR}"
mkdir -p "$out"
test ! -e "$out/install.log"
exec > >(tee "$out/install.log") 2>&1
set -x
date -u
helm repo add gatekeeper https://open-policy-agent.github.io/gatekeeper/charts --force-update
helm repo update gatekeeper
helm upgrade --install gatekeeper gatekeeper/gatekeeper --kube-context "$context" \
  --namespace gatekeeper-system --create-namespace --version 3.23.1 \
  --values policies/gatekeeper/local-values.yaml --wait --timeout 5m
kubectl --context "$context" apply -f policies/gatekeeper/nonroot-template.yaml
kubectl --context "$context" wait --for=condition=Established crd/team4nonroot.constraints.gatekeeper.sh --timeout=120s
kubectl --context "$context" apply -f policies/gatekeeper/nonroot-constraint.yaml
kubectl --context "$context" get constrainttemplate team4nonroot -o yaml > "$out/template.yaml"
kubectl --context "$context" get team4nonroot son-require-nonroot -o yaml > "$out/constraint.yaml"
kubectl --context "$context" -n gatekeeper-system get pods -o wide
