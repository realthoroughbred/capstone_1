#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
context=kind-team4
server="$(kubectl --context "$context" config view --minify -o jsonpath='{.clusters[0].cluster.server}')"
[[ "$server" == https://127.0.0.1:* || "$server" == https://localhost:* ]]
: "${EVIDENCE_DIR:?Fresh evidence directory required}"
mkdir "$EVIDENCE_DIR"
name="team4readiness$(date +%s)"
test -z "$(kubectl --context "$context" get constrainttemplate "$name" --ignore-not-found -o name)"
python3 - "$name" > "$EVIDENCE_DIR/template.yaml" <<'PY'
import sys,yaml
doc=yaml.safe_load(open('policies/gatekeeper/nonroot-template.yaml'))
doc['metadata']['name']=sys.argv[1]
doc['spec']['crd']['spec']['names']['kind']=sys.argv[1]
print(yaml.safe_dump(doc))
PY
cleanup() { kubectl --context "$context" delete constrainttemplate "$name" --ignore-not-found --wait=true; }
trap cleanup EXIT
kubectl --context "$context" apply -f "$EVIDENCE_DIR/template.yaml"
kubectl --context "$context" wait --for=create "crd/$name.constraints.gatekeeper.sh" --timeout=120s
kubectl --context "$context" wait --for=condition=Established "crd/$name.constraints.gatekeeper.sh" --timeout=120s
kubectl --context "$context" wait --for=jsonpath='{.status.created}'=true "constrainttemplate/$name" --timeout=120s
kubectl --context "$context" get constrainttemplate "$name" -o json > "$EVIDENCE_DIR/created.json"
echo 'PASS: previously absent template and generated CRD became ready; test-owned template is removed.'
