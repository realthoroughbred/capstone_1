#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

REGISTRY="127.0.0.1:5000"
IMAGE="$REGISTRY/team4-test:ci"
KEY_DIR="$HOME/.config/team4-cosign"

mkdir -p reports

echo "[1/5] 로컬 Registry 확인"
curl -fsS "http://$REGISTRY/v2/" > /dev/null

echo "[2/5] Trivy 보안 검사"
trivy image \
  --scanners vuln \
  --severity HIGH,CRITICAL \
  --exit-code 1 \
  --format json \
  --output reports/trivy.json \
  team4-test:ci

echo "[3/5] 이미지 Push"
docker tag team4-test:ci "$IMAGE"

PUSH_LOG=$(mktemp)
trap 'rm -f "$PUSH_LOG"' EXIT

docker push "$IMAGE" | tee "$PUSH_LOG"

DIGEST=$(sed -n 's/.*digest: \(sha256:[0-9a-f]*\).*/\1/p' "$PUSH_LOG" | tail -n 1)

if [[ -z "$DIGEST" ]]; then
  echo "이미지 Digest 확인 실패"
  exit 1
fi

SIGNED_IMAGE="$REGISTRY/team4-test@$DIGEST"

echo "[4/5] cosign 이미지 서명"
cosign sign \
  --key "$KEY_DIR/cosign.key" \
  --signing-config "$KEY_DIR/signing-config.json" \
  --allow-http-registry \
  --yes \
  "$SIGNED_IMAGE"

echo "[5/5] 공개키 서명 검증"
cosign verify \
  --key "$KEY_DIR/cosign.pub" \
  --allow-http-registry \
  --insecure-ignore-tlog \
  "$SIGNED_IMAGE" > reports/cosign-verify.json

echo "===== 자동화 완료 ====="
echo "이미지: $SIGNED_IMAGE"
echo "검증 결과: reports/cosign-verify.json"
