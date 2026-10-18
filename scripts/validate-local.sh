#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export PATH="$PWD/.venv-ci/bin:$PWD/.tools/bin:$PATH"
mkdir -p evidence/local
python3 -m unittest discover -s tests -v 2>&1 | tee evidence/local/unit-tests.txt
find scripts automation -name '*.sh' -print0 | xargs -0 -r -n1 bash -n
python3 - <<'PY'
from pathlib import Path
import yaml
for folder in ('k8s', 'policies', '.github', 'config', 'automation'):
    for path in Path(folder).rglob('*.yaml'):
        list(yaml.safe_load_all(path.read_text()))
    for path in Path(folder).rglob('*.yml'):
        list(yaml.safe_load_all(path.read_text()))
print('PASS: YAML syntax')
PY
bash scripts/image-security.sh 2>&1 | tee evidence/local/image-security.txt
bash scripts/local-signature-test.sh 2>&1 | tee evidence/local/signature.txt
