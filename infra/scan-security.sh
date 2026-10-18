#!/usr/bin/env bash
set -euo pipefail
repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_dir"
mkdir -p evidence/terraform
checkov_bin="${CHECKOV_BIN:-checkov}"
if ! command -v "$checkov_bin" >/dev/null 2>&1 && [[ -x .venv-ci/bin/checkov ]]; then
  checkov_bin="$repo_dir/.venv-ci/bin/checkov"
fi
set +e
"$checkov_bin" -d infra --framework terraform --skip-download -o json > evidence/terraform/checkov.json
scan_status=$?
set -e
printf '%s\n' "$scan_status" > evidence/terraform/checkov-exit-code.txt
python3 -c 'import json; r=json.load(open("evidence/terraform/checkov.json")); print(json.dumps(r["summary"],sort_keys=True))'
exit "$scan_status"
