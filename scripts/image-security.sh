#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export PATH="$PWD/.tools/bin:$PATH"
out="${EVIDENCE_DIR:-evidence/image}"
mkdir -p "$out"
# Alpine still uses BusyBox httpd/wget, while its APK database makes scans auditable.
# The original bare BusyBox image has no Trivy package inventory (see baseline evidence).
base="${BASE_IMAGE:-alpine:3.23.6}"
docker pull --platform linux/amd64 "$base"
base_digest="$(docker image inspect "$base" --format '{{index .RepoDigests 0}}')"
[[ "$base_digest" =~ @sha256:[0-9a-f]{64}$ ]]
printf '%s\n' "$base_digest" > "$out/base-image.txt"
docker build --platform linux/amd64 --provenance=false --sbom=false --build-arg "BASE_IMAGE=$base_digest" -t team4-test:v1 containers/test
docker image inspect team4-test:v1 > "$out/image-inspect.json"
docker image inspect team4-test:v1 --format '{{.Id}}' > "$out/image-store-id.txt"
cid="$(docker run -d --read-only --cap-drop ALL --security-opt no-new-privileges team4-test:v1)"
cleanup() { docker logs "$cid" > "$out/container.log" 2>&1; docker rm -f "$cid" >/dev/null; }
trap cleanup EXIT
for attempt in $(seq 1 20); do
  if docker exec "$cid" wget -T 2 -qO- http://127.0.0.1:8080 > "$out/http-response.txt"; then break; fi
  sleep 1
done
grep -Fx 'team4 server ok' "$out/http-response.txt"
docker save "$(cat "$out/image-store-id.txt")" -o "$out/image.tar"
python3 scripts/archive-config-digest.py "$out/image.tar" > "$out/image-config-digest.txt"
sha256sum "$out/image.tar" > "$out/image-tar.sha256"
# Always retain a complete report before enforcing severity. Operational errors fail closed.
trivy image --input "$out/image.tar" --scanners vuln --list-all-pkgs --quiet --format json --output "$out/trivy.json"
python3 scripts/check-image-report.py "$out/trivy.json"
syft "docker-archive:$out/image.tar" -o "cyclonedx-json=$out/sbom.cdx.json"
python3 scripts/validate-sbom.py "$out/sbom.cdx.json" "$out/image-config-digest.txt" "$out/sbom-link.json"
trivy image --input "$out/image.tar" --scanners vuln --severity HIGH,CRITICAL --exit-code 1 --format table > "$out/trivy-gate.txt"
printf 'PASS: build, HTTP, vulnerability gate and SBOM. Registry signature is a separate stage.\n'
