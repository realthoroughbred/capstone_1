#!/usr/bin/env bash
# Configuration and mock-provider checks only; never plans/applies against AWS.
set -euo pipefail
repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_dir"
mkdir -p evidence/terraform
trap 'validation_status=$?; printf "%s\n" "$validation_status" > evidence/terraform/validation-exit-code.txt' EXIT
date -u +%Y-%m-%dT%H:%M:%SZ > evidence/terraform/recorded-at.txt
terraform version -json > evidence/terraform/version.json
terraform -chdir=infra fmt -check -recursive -no-color > evidence/terraform/fmt.txt
terraform -chdir=infra init -backend=false -input=false -lockfile=readonly -no-color > evidence/terraform/init.txt
terraform -chdir=infra validate -json > evidence/terraform/validate.json
test_status=0
bash infra/test-isolated.sh > evidence/terraform/mock-tests.txt 2>&1 || test_status=$?
cat evidence/terraform/mock-tests.txt
exit "$test_status"
