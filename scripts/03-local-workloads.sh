#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p evidence
# Resolve a base tag once. Reuse the recorded digest for reproducible team builds.
base_tag="${BASE_TAG:-busybox:1.37.0}"
docker pull --platform linux/amd64 "$base_tag"
base_ref="$(docker image inspect "$base_tag" --format '{{index .RepoDigests 0}}')"
[[ "$base_ref" == *@sha256:* ]]
printf '%s\n' "$base_ref" > evidence/base-image.txt
docker build --platform linux/amd64 --build-arg "BASE_IMAGE=$base_ref" -t team4-test:v1 containers/test
kind load docker-image team4-test:v1 --name team4
kubectl --context kind-team4 apply -f k8s/namespace.yaml
kubectl --context kind-team4 apply -f k8s/workloads.yaml
for app in server client unauthorized; do
  kubectl --context kind-team4 rollout status "deployment/$app" -n demo --timeout=180s
done
kubectl --context kind-team4 -n demo exec deployment/client -- wget -T 5 -qO- http://server:8080
kubectl --context kind-team4 -n demo exec deployment/unauthorized -- wget -T 5 -qO- http://server:8080
