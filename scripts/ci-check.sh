#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p evidence/ci
python3 -m unittest discover -s tests -v 2>&1 | tee evidence/ci/unit-tests.txt
find scripts automation -name '*.sh' -print0 | xargs -0 -r -n1 bash -n
terraform -chdir=infra fmt -check -recursive
terraform -chdir=infra init -backend=false -input=false -lockfile=readonly
terraform -chdir=infra validate -json | tee evidence/ci/terraform-validate.json
terraform -chdir=infra test -no-color | tee evidence/ci/terraform-mock-tests.txt
set +e
checkov --config-file .checkov.yaml --output json > evidence/ci/checkov.json
rc=$?
set -e
python3 - "$rc" <<'PY'
import json, sys
from pathlib import Path
data = json.loads(Path('evidence/ci/checkov.json').read_text())
reports = data if isinstance(data, list) else [data]
for report in reports:
    print(json.dumps(report.get('summary', {})))
sys.exit(int(sys.argv[1]))
PY
