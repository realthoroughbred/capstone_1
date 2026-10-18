#!/usr/bin/env bash
set -euo pipefail
source config/versions.env
[[ "$(uname -s)" == Linux && "$(uname -m)" == x86_64 ]] || { echo 'Linux x86_64 worker required' >&2; exit 1; }
work_dir=$(mktemp -d)
trap 'rm -f "$work_dir/kubectl" "$work_dir/kubectl.sha256"; rmdir "$work_dir"' EXIT
curl --fail --silent --show-error --location --proto '=https' --tlsv1.2 \
  "https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/amd64/kubectl" -o "$work_dir/kubectl"
curl --fail --silent --show-error --location --proto '=https' --tlsv1.2 \
  "https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/amd64/kubectl.sha256" -o "$work_dir/kubectl.sha256"
printf '%s  %s\n' "$(cat "$work_dir/kubectl.sha256")" "$work_dir/kubectl" | sha256sum --check --status
mkdir -p .tools/bin
install -m 0755 "$work_dir/kubectl" .tools/bin/kubectl
.tools/bin/kubectl version --client=true
