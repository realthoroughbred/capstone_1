#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/lib-k8s.sh
source config/security-versions.env
require_demo_context "${1:?Usage: 07-install-security-addons.sh CONTEXT [eso|kyverno|argocd|all]}"
component="${2:-all}"
case "$component" in eso|kyverno|argocd|all) ;; *) exit 1 ;; esac
mkdir -p evidence
if [[ "$component" == eso || "$component" == all ]]; then
  helm repo add external-secrets https://charts.external-secrets.io --force-update
  helm repo update external-secrets
  helm upgrade --install external-secrets external-secrets/external-secrets --kube-context "$context" \
    --namespace external-secrets --create-namespace --version "$ESO_CHART_VERSION" \
    --set installCRDs=true --wait --timeout 10m
fi
if [[ "$component" == kyverno || "$component" == all ]]; then
  helm repo add kyverno https://kyverno.github.io/kyverno --force-update
  helm repo update kyverno
  helm upgrade --install kyverno kyverno/kyverno --kube-context "$context" \
    --namespace kyverno --create-namespace --version "$KYVERNO_CHART_VERSION" \
    --set admissionController.replicas=1 --wait --timeout 10m
  "${k[@]}" apply -f policies/kyverno/restricted.yaml
fi
if [[ "$component" == argocd || "$component" == all ]]; then
  helm repo add argo https://argoproj.github.io/argo-helm --force-update
  helm repo update argo
  helm upgrade --install argocd argo/argo-cd --kube-context "$context" \
    --namespace argocd --create-namespace --version "$ARGOCD_CHART_VERSION" \
    --set dex.enabled=false --set notifications.enabled=false --set applicationSet.replicas=0 \
    --set server.service.type=ClusterIP --wait --timeout 10m
fi
helm --kube-context "$context" list -A -o json > "evidence/addons-${context}.json"
