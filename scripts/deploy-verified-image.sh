#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export PATH="$PWD/.tools/bin:$PATH"
: "${EXPECTED_ACCOUNT_ID:?}" "${AWS_REGION:?}" "${ECR_REPOSITORY:?}" "${COSIGN_IDENTITY:?}"
[[ "$(aws sts get-caller-identity --query Account --output text)" == "$EXPECTED_ACCOUNT_ID" ]]
image="$(cat evidence/deployed-image.txt)"
[[ "$image" == "$ECR_REPOSITORY@sha256:"* ]]
[[ "${image##*@}" =~ ^sha256:[0-9a-f]{64}$ ]]
cosign verify --certificate-identity "$COSIGN_IDENTITY" --certificate-oidc-issuer https://token.actions.githubusercontent.com "$image" > evidence/cosign-verify.json
cosign verify-attestation --certificate-identity "$COSIGN_IDENTITY" --certificate-oidc-issuer https://token.actions.githubusercontent.com --type cyclonedx "$image" > evidence/image/attestation-deploy-verify.json
aws eks update-kubeconfig --name "${EKS_CLUSTER:-team4-eks}" --region "$AWS_REGION" --alias team4-eks
mkdir -p generated
sed "s|image: team4-test:v1|image: $image|g" k8s/workloads.yaml > generated/workloads-eks.yaml
# Namespace, ESO, admission policies and GitOps are operator bootstraps; deployment role cannot weaken them.
kubectl --context team4-eks get namespace demo >/dev/null
kubectl --context team4-eks apply -f generated/workloads-eks.yaml
for app in server client unauthorized; do
  kubectl --context team4-eks -n demo rollout status "deployment/$app" --timeout=300s
done
python3 scripts/verify-deployed-images.py --context team4-eks --namespace demo --image "$image"
kubectl --context team4-eks -n demo exec deployment/client -- wget -T 5 -qO- http://server:8080 | tee evidence/deployment-http.txt
grep -Fx 'team4 server ok' evidence/deployment-http.txt
kubectl --context team4-eks -n demo get pods,deployments -o wide > evidence/deployment-status.txt
