#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export PATH="$PWD/.tools/bin:$PATH"
: "${EXPECTED_ACCOUNT_ID:?set expected account}" "${ECR_REPOSITORY:?set repository URL}" "${AWS_REGION:?set region}" "${COSIGN_IDENTITY:?set exact trusted workflow identity}"
tag="${1:?supply immutable unique tag}"
[[ "$tag" =~ ^[a-zA-Z0-9_][a-zA-Z0-9_.-]{0,127}$ ]]
[[ "$(aws sts get-caller-identity --query Account --output text)" == "$EXPECTED_ACCOUNT_ID" ]]
[[ "$ECR_REPOSITORY" == "$EXPECTED_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/"* ]]
test -s evidence/image/sbom-link.json
config_digest="$(cat evidence/image/image-config-digest.txt)"
store_id="$(cat evidence/image/image-store-id.txt)"
[[ "$config_digest" =~ ^sha256:[0-9a-f]{64}$ ]]
sha256sum --check evidence/image/image-tar.sha256
test "$(python3 scripts/archive-config-digest.py evidence/image/image.tar)" = "$config_digest"
test "$(docker image inspect "$store_id" --format '{{.Id}}')" = "$store_id"
# Re-evaluate the exact saved image, not a mutable remote tag.
trivy image --input evidence/image/image.tar --scanners vuln --severity HIGH,CRITICAL --exit-code 1
aws ecr get-login-password --region "$AWS_REGION" | docker login --username AWS --password-stdin "${ECR_REPOSITORY%%/*}"
docker tag "$store_id" "$ECR_REPOSITORY:$tag"
docker push "$ECR_REPOSITORY:$tag"
digest="$(aws ecr describe-images --region "$AWS_REGION" --repository-name "${ECR_REPOSITORY#*/}" --image-ids "imageTag=$tag" --query 'imageDetails[0].imageDigest' --output text)"
[[ "$digest" =~ ^sha256:[0-9a-f]{64}$ ]]
image="$ECR_REPOSITORY@$digest"
aws ecr batch-get-image --region "$AWS_REGION" --repository-name "${ECR_REPOSITORY#*/}" --image-ids "imageDigest=$digest" > evidence/image/registry-manifest.json
python3 - "$config_digest" <<'PY'
import json, sys
from pathlib import Path
response=json.loads(Path('evidence/image/registry-manifest.json').read_text())
manifest=json.loads(response['images'][0]['imageManifest'])
if manifest['config']['digest'] != sys.argv[1]:
    raise SystemExit('Registry manifest differs from scanned image')
PY
trivy image --scanners vuln --severity HIGH,CRITICAL --exit-code 1 "$image"
cosign sign --yes "$image"
cosign attest --yes --predicate evidence/image/sbom.cdx.json --type cyclonedx "$image"
cosign verify --certificate-identity "$COSIGN_IDENTITY" --certificate-oidc-issuer https://token.actions.githubusercontent.com "$image" > evidence/cosign-verify.json
cosign verify-attestation --certificate-identity "$COSIGN_IDENTITY" --certificate-oidc-issuer https://token.actions.githubusercontent.com --type cyclonedx "$image" > evidence/image/attestation-verify.json
printf '%s\n' "$image" > evidence/deployed-image.txt
python3 - "$image" <<'PY'
import json, sys
from pathlib import Path
doc=json.loads(Path('evidence/image/sbom-link.json').read_text())
doc['registry_manifest_digest']=sys.argv[1].split('@')[1]
doc['image_reference']=sys.argv[1]
Path('evidence/registry-binding.json').write_text(json.dumps(doc, indent=2)+'\n')
PY
