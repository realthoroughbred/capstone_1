#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
out="${CI_EVIDENCE_DIR:-evidence/ci}"
mkdir -p "$out"
python3 -m unittest discover -s tests -v 2>&1 | tee "$out/unit-tests.txt"
find scripts automation infra -name '*.sh' -print0 | xargs -0 -r -n1 bash -n
terraform -chdir=infra fmt -check -recursive
terraform -chdir=infra init -backend=false -input=false -lockfile=readonly
terraform -chdir=infra validate -json | tee "$out/terraform-validate.json"
bash infra/test-isolated.sh | tee "$out/terraform-mock-tests.txt"
set +e
python3 scripts/security_scan.py --tool checkov --output "$out/checkov.json" --target infra --stdout-json -- \
  checkov --config-file .checkov.yaml --output json
rc=$?
set -e
python3 - "$rc" "$out/checkov.json" <<'PY'
import json, sys
from pathlib import Path
data = json.loads(Path(sys.argv[2]).read_text())
reports = data if isinstance(data, list) else [data]
for report in reports:
    print(json.dumps(report.get('summary', {})))
sys.exit(int(sys.argv[1]))
PY
