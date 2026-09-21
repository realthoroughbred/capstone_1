#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
source config/versions.env
docker info >/dev/null
if kind get clusters | awk '$0 == "team4" {found=1} END {exit !found}'; then
  echo 'Existing team4 cluster found. It must have been created with config/kind.yaml.'
else
  # Do not add --wait here: the CNI has intentionally not been installed yet.
  kind create cluster --name team4 --image "$KIND_NODE_IMAGE" --config config/kind.yaml
fi
mkdir -p downloads/calico
for file in v1_crd_projectcalico_org.yaml tigera-operator.yaml; do
  curl -fL --retry 2 "https://raw.githubusercontent.com/projectcalico/calico/${CALICO_VERSION}/manifests/${file}" -o "downloads/calico/${file}"
  kubectl --context kind-team4 apply --server-side -f "downloads/calico/${file}"
done
kubectl --context kind-team4 wait --for=condition=Established crd/installations.operator.tigera.io --timeout=120s
kubectl --context kind-team4 apply -f config/calico-installation.yaml
kubectl --context kind-team4 wait --for=condition=Ready nodes --all --timeout=600s
kubectl --context kind-team4 rollout status deployment/coredns -n kube-system --timeout=300s
kubectl --context kind-team4 get nodes
kubectl --context kind-team4 get pods -A
