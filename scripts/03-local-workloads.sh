#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p evidence
# Keep the exact image that passed the scanner/SBOM stage through kind loading.
checked_id="$(cat evidence/image/image-store-id.txt 2>/dev/null || true)"
current_id="$(docker image inspect team4-test:v1 --format '{{.Id}}' 2>/dev/null || true)"
if [[ -z "$checked_id" || "$checked_id" != "$current_id" || "${REBUILD_IMAGE:-false}" == true ]]; then
  bash scripts/image-security.sh
fi
python3 scripts/check-image-report.py evidence/image/trivy.json
python3 - <<'PY'
import json
from pathlib import Path
report = json.loads(Path('evidence/image/trivy.json').read_text())
if any(v.get('Severity') in {'HIGH', 'CRITICAL'}
       for result in report.get('Results', []) for v in result.get('Vulnerabilities', [])):
    raise SystemExit('Image has HIGH/CRITICAL findings; refusing kind deployment')
PY
[[ "$(cat evidence/image/image-store-id.txt)" == "$(docker image inspect team4-test:v1 --format '{{.Id}}')" ]]
checked_id="$(cat evidence/image/image-store-id.txt)"
local_image="team4-test:local-${checked_id#sha256:}"
docker tag "$checked_id" "$local_image"
kind load docker-image "$local_image" --name team4
kubectl --context kind-team4 apply -f k8s/namespace.yaml
python3 - "$local_image" <<'PY' | kubectl --context kind-team4 apply -f -
import sys, yaml
from pathlib import Path
documents = list(yaml.safe_load_all(Path('k8s/workloads.yaml').read_text()))
for document in documents:
    if document and document.get('kind') == 'Deployment':
        for container in document['spec']['template']['spec']['containers']:
            container['image'] = sys.argv[1]
print(yaml.safe_dump_all(documents))
PY
for app in server client unauthorized; do
  kubectl --context kind-team4 rollout status "deployment/$app" -n demo --timeout=180s
done
kubectl --context kind-team4 -n demo exec deployment/client -- wget -T 5 -qO- http://server:8080
# Keep deny-by-default policies installed after the test; reruns are supported.
bash scripts/08-network-policy-test.sh kind-team4
