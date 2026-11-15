#!/usr/bin/env bash
# Execute only in an approved AWS test window. Does not inherit the active context.
set -euo pipefail
cd "$(dirname "$0")/.."
test "${APPROVE_AWS_TEST:-false}" = true
: "${EXPECTED_ACCOUNT_ID:?Set the approved account}" "${AWS_REGION:?Set the approved region}"
context=team4-eks
cluster="${CLUSTER_NAME:-team4-eks}"
test "$(aws sts get-caller-identity --query Account --output text)" = "$EXPECTED_ACCOUNT_ID"
endpoint="$(aws eks describe-cluster --region "$AWS_REGION" --name "$cluster" --query cluster.endpoint --output text)"
test "$(kubectl --context "$context" config view --minify -o jsonpath='{.clusters[0].cluster.server}')" = "$endpoint"
for permission in 'create customresourcedefinitions.apiextensions.k8s.io' 'create clusterroles.rbac.authorization.k8s.io' 'create validatingwebhookconfigurations.admissionregistration.k8s.io'; do
  read -r verb resource <<< "$permission"
  test "$(kubectl --context "$context" auth can-i "$verb" "$resource")" = yes
done
helm repo add gatekeeper https://open-policy-agent.github.io/gatekeeper/charts --force-update
helm repo update gatekeeper
helm upgrade --install gatekeeper gatekeeper/gatekeeper --kube-context "$context" --namespace gatekeeper-system \
  --create-namespace --version 3.23.1 --values policies/gatekeeper/eks-values.yaml --wait --timeout 8m
kubectl --context "$context" apply -f policies/gatekeeper/nonroot-template.yaml
kubectl --context "$context" wait --for=create crd/team4nonroot.constraints.gatekeeper.sh --timeout=180s
kubectl --context "$context" wait --for=condition=Established crd/team4nonroot.constraints.gatekeeper.sh --timeout=120s
kubectl --context "$context" wait --for=jsonpath='{.status.created}'=true constrainttemplate/team4nonroot --timeout=120s
kubectl --context "$context" apply -f policies/gatekeeper/nonroot-constraint.yaml
