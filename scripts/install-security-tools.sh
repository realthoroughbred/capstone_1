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
fetch_verified() {
  local url="$1" file="$2" checksum="$3"
  # Fresh upstream checksum, then validate every cached archive before extraction.
  if [[ "${SECURITY_CACHE_MODE:-on}" != off && -f "$file" ]] && verify "$checksum" "$file"; then
    printf 'Verified archive cache hit: %s\n' "$file"
  else
    fetch "$url" "$file"
    verify "$checksum" "$file"
  fi
}
file="trivy_${TRIVY_VERSION}_Linux-64bit.tar.gz"
base="https://github.com/aquasecurity/trivy/releases/download/v${TRIVY_VERSION}"
fetch "$base/trivy_${TRIVY_VERSION}_checksums.txt" trivy-checksums.txt
fetch_verified "$base/$file" "$file" trivy-checksums.txt
tar -xzf "$file" -C "$root/.tools/bin" trivy
file="syft_${SYFT_VERSION}_linux_amd64.tar.gz"
base="https://github.com/anchore/syft/releases/download/v${SYFT_VERSION}"
fetch "$base/syft_${SYFT_VERSION}_checksums.txt" syft-checksums.txt
fetch_verified "$base/$file" "$file" syft-checksums.txt
tar -xzf "$file" -C "$root/.tools/bin" syft
base="https://github.com/sigstore/cosign/releases/download/v${COSIGN_VERSION}"
fetch "$base/cosign_checksums.txt" cosign-checksums.txt
fetch_verified "$base/cosign-linux-amd64" cosign-linux-amd64 cosign-checksums.txt
install -m 0755 cosign-linux-amd64 "$root/.tools/bin/cosign"
"$root/.tools/bin/trivy" --version
"$root/.tools/bin/syft" version
"$root/.tools/bin/cosign" version
