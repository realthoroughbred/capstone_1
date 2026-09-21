#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
source config/versions.env
if [[ "$(uname -s)" != Linux || "$(uname -m)" != x86_64 ]]; then
  echo 'This installer is for WSL2 Ubuntu / Linux x86_64.' >&2
  exit 1
fi
sudo apt-get update
sudo apt-get install -y git curl unzip ca-certificates jq
mkdir -p downloads/tools
cd downloads/tools
curl -fL --retry 2 "https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/amd64/kubectl" -o kubectl
curl -fL --retry 2 "https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/amd64/kubectl.sha256" -o kubectl.sha256
printf '%s  kubectl\n' "$(cat kubectl.sha256)" | sha256sum --check
sudo install -m 0755 kubectl /usr/local/bin/kubectl
curl -fL --retry 2 "https://kind.sigs.k8s.io/dl/${KIND_VERSION}/kind-linux-amd64" -o kind
sudo install -m 0755 kind /usr/local/bin/kind
curl -fL --retry 2 "https://get.helm.sh/helm-${HELM_VERSION}-linux-amd64.tar.gz" -o helm.tar.gz
curl -fL --retry 2 "https://get.helm.sh/helm-${HELM_VERSION}-linux-amd64.tar.gz.sha256sum" -o helm.sha256
mv helm.tar.gz "helm-${HELM_VERSION}-linux-amd64.tar.gz"
sha256sum --check helm.sha256
tar -xzf "helm-${HELM_VERSION}-linux-amd64.tar.gz"
sudo install -m 0755 linux-amd64/helm /usr/local/bin/helm
tf_file="terraform_${TERRAFORM_VERSION}_linux_amd64.zip"
curl -fL --retry 2 "https://releases.hashicorp.com/terraform/${TERRAFORM_VERSION}/${tf_file}" -o "$tf_file"
curl -fL --retry 2 "https://releases.hashicorp.com/terraform/${TERRAFORM_VERSION}/terraform_${TERRAFORM_VERSION}_SHA256SUMS" -o terraform.sha256
awk -v f="$tf_file" '$2 == f' terraform.sha256 > terraform-selected.sha256
test -s terraform-selected.sha256
sha256sum --check terraform-selected.sha256
unzip -o "$tf_file" -d terraform-extract
sudo install -m 0755 terraform-extract/terraform /usr/local/bin/terraform
# AWS CLI v2: record the resolved version below and use the same version on teammates' PCs.
curl -fL --retry 2 https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip -o awscliv2.zip
unzip -oq awscliv2.zip
sudo ./aws/install --update
git --version
kubectl version --client
kind version
helm version --short
terraform version
aws --version
