#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export PATH="$PWD/.tools/bin:$PATH"
out="${EVIDENCE_DIR:-evidence/local-signature}"
mkdir -p "$out"
out="$(cd "$out" && pwd)"
# Ephemeral local registry/key are test-only. AWS keyless verification remains a separate test.
name="team4-signature-test-$RANDOM"
docker network create "$name" >/dev/null
registry=''
cleanup() {
  if [[ -n "$registry" ]]; then docker rm -f "$registry" >/dev/null; fi
  docker network rm "$name" >/dev/null
}
trap cleanup EXIT
registry="$(docker run -d --platform linux/amd64 --name "$name" --network "$name" --network-alias registry registry:2)"
# Keep the registry private to this Docker network. This also works with WSL/Desktop
# whose host loopback differs from the daemon's loopback.
ref='127.0.0.1:5000/team4-test:test'
# Docker save creates a 0600 archive on native Linux. Match its owner instead of
# relying on Docker Desktop's more permissive Windows-mounted filesystem.
crane=(docker run --rm --platform linux/amd64 --user "$(id -u):$(id -g)" --network "container:$registry" -v "$PWD/evidence/image/image.tar:/work/image.tar:ro" gcr.io/go-containerregistry/crane:v0.20.3)
registry_ready=false
for attempt in {1..30}; do
  if "${crane[@]}" catalog --insecure 127.0.0.1:5000 >/dev/null 2>&1; then
    registry_ready=true; break
  fi
  sleep 1
done
[[ "$registry_ready" == true ]] || { echo 'FAIL: local registry did not become ready' >&2; exit 1; }
"${crane[@]}" push --insecure /work/image.tar "$ref" > "$out/push.txt"
digest="$("${crane[@]}" digest --insecure "$ref")"
[[ "$digest" =~ ^sha256:[0-9a-f]{64}$ ]]
image="127.0.0.1:5000/team4-test@$digest"
export COSIGN_PASSWORD
COSIGN_PASSWORD="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
keyname="test-only-$RANDOM-$RANDOM"
cosign generate-key-pair --output-key-prefix "$out/$keyname" >/dev/null
signer=(docker run --rm --platform linux/amd64 --network "container:$registry" -e COSIGN_PASSWORD -v "$out:/work" -v "$PWD/.tools/bin/cosign:/usr/local/bin/cosign:ro" alpine:3.23.6 cosign)
"${signer[@]}" sign --yes --key "/work/$keyname.key" --tlog-upload=false --allow-http-registry "$image"
"${signer[@]}" verify --key "/work/$keyname.pub" --insecure-ignore-tlog --allow-http-registry "$image" > "$out/verify.json"
cosign generate-key-pair --output-key-prefix "$out/wrong-$keyname" >/dev/null
if "${signer[@]}" verify --key "/work/wrong-$keyname.pub" --insecure-ignore-tlog --allow-http-registry "$image" > "$out/wrong-key.txt" 2>&1; then
  echo 'FAIL: wrong signing key accepted' >&2; exit 1
fi
if ! grep -Fq 'no matching signatures' "$out/wrong-key.txt" || ! grep -Fq 'invalid signature' "$out/wrong-key.txt"; then
  echo 'FAIL: wrong-key verification failed for an unexpected operational reason' >&2
  exit 1
fi
printf '%s\n' "$image" > "$out/signed-image.txt"
printf 'PASS: local cryptographic signature and wrong-key rejection; no OIDC or transparency-log assertion.\n'
