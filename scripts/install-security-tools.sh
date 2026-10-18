#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
source config/security-tools.env
[[ "$(uname -s)-$(uname -m)" == Linux-x86_64 ]] || { echo 'Linux x86_64 required' >&2; exit 1; }
mkdir -p .tools/bin downloads/security
root="$PWD"
cd downloads/security
fetch() { curl --fail --location --retry 3 --connect-timeout 20 "$1" --output "$2"; }
verify() {
  local checksum="$1" file="$2"
  awk -v file="$file" '$2 == file || $2 == "*"file' "$checksum" > selected.sha256
  test -s selected.sha256
  sha256sum --check selected.sha256
}
file="trivy_${TRIVY_VERSION}_Linux-64bit.tar.gz"
base="https://github.com/aquasecurity/trivy/releases/download/v${TRIVY_VERSION}"
fetch "$base/$file" "$file"
fetch "$base/trivy_${TRIVY_VERSION}_checksums.txt" trivy-checksums.txt
verify trivy-checksums.txt "$file"
tar -xzf "$file" -C "$root/.tools/bin" trivy
file="syft_${SYFT_VERSION}_linux_amd64.tar.gz"
base="https://github.com/anchore/syft/releases/download/v${SYFT_VERSION}"
fetch "$base/$file" "$file"
fetch "$base/syft_${SYFT_VERSION}_checksums.txt" syft-checksums.txt
verify syft-checksums.txt "$file"
tar -xzf "$file" -C "$root/.tools/bin" syft
base="https://github.com/sigstore/cosign/releases/download/v${COSIGN_VERSION}"
fetch "$base/cosign-linux-amd64" cosign-linux-amd64
fetch "$base/cosign_checksums.txt" cosign-checksums.txt
verify cosign-checksums.txt cosign-linux-amd64
install -m 0755 cosign-linux-amd64 "$root/.tools/bin/cosign"
"$root/.tools/bin/trivy" --version
"$root/.tools/bin/syft" version
"$root/.tools/bin/cosign" version
