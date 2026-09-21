#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
source config/versions.env
aws sts get-caller-identity --query '{Account:Account,Arn:Arn}'
mkdir -p generated
for addon in vpc-cni kube-proxy coredns; do
  aws eks describe-addon-versions --region "$AWS_REGION" --kubernetes-version "$EKS_VERSION" --addon-name "$addon" --output json > "generated/${addon}-versions.json"
done
jq -n \
  --slurpfile cni generated/vpc-cni-versions.json \
  --slurpfile proxy generated/kube-proxy-versions.json \
  --slurpfile dns generated/coredns-versions.json '
  def recommended: [.addons[0].addonVersions[] | select(any(.compatibilities[]; .defaultVersion == true)) | .addonVersion][0];
  {addon_versions: {"vpc-cni": ($cni[0] | recommended), "kube-proxy": ($proxy[0] | recommended), coredns: ($dns[0] | recommended)}}
  | if any(.addon_versions[]; . == null) then error("No compatible default addon version found") else . end
  ' > generated/addons.auto.tfvars.json
# Refuse a CNI older than the documented prerequisite used by this guide.
jq -e '.addon_versions["vpc-cni"] | capture("^v(?<major>[0-9]+)\\.(?<minor>[0-9]+)") | ((.major|tonumber)>1 or ((.major|tonumber)==1 and (.minor|tonumber)>=21))' generated/addons.auto.tfvars.json >/dev/null
cp generated/addons.auto.tfvars.json infra/addons.auto.tfvars.json
cat infra/addons.auto.tfvars.json
