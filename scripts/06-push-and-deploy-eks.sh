#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
tag="${1:?Usage: bash scripts/06-push-and-deploy-eks.sh v1}"
[[ "$tag" =~ ^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$ ]]
region="$(terraform -chdir=infra output -raw region)"
cluster="$(terraform -chdir=infra output -raw cluster_name)"
repo="$(terraform -chdir=infra output -raw repository_url)"
repo_name="$(terraform -chdir=infra output -raw repository_name)"
account="$(aws sts get-caller-identity --query Account --output text)"
[[ "$repo" == "$account".dkr.ecr.* ]] || { echo 'Wrong AWS account.' >&2; exit 1; }
aws ecr get-login-password --region "$region" | docker login --username AWS --password-stdin "${repo%%/*}"
docker image inspect team4-test:v1 >/dev/null
docker tag team4-test:v1 "${repo}:${tag}"
docker push "${repo}:${tag}"
digest="$(aws ecr describe-images --region "$region" --repository-name "$repo_name" --image-ids "imageTag=$tag" --query 'imageDetails[0].imageDigest' --output text)"
[[ "$digest" == sha256:* ]]
image_ref="${repo}@${digest}"
mkdir -p generated evidence
printf '%s\n' "$image_ref" > evidence/deployed-image.txt
# Every test Deployment uses the same exact ECR digest.
sed "s|image: team4-test:v1|image: ${image_ref}|g" k8s/workloads.yaml > generated/workloads-eks.yaml
aws eks update-kubeconfig --region "$region" --name "$cluster" --alias team4-eks
kubectl --context team4-eks auth can-i create deployments -n demo
kubectl --context team4-eks apply -f k8s/namespace.yaml
kubectl --context team4-eks apply -f generated/workloads-eks.yaml
for app in server client unauthorized; do
  kubectl --context team4-eks rollout status "deployment/$app" -n demo --timeout=300s
done
kubectl --context team4-eks -n demo exec deployment/client -- wget -T 5 -qO- http://server:8080
kubectl --context team4-eks -n demo get pods -o wide
printf 'Deployed image: %s\n' "$image_ref"
