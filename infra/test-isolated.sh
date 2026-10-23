#!/usr/bin/env bash
# Exercise configuration defaults without loading deployment tfvars or Terraform state.
set -euo pipefail
repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
scratch_dir="$(mktemp -d /tmp/team4-terraform-tests.XXXXXX)"
cleanup() {
  # Only remove this script's mktemp directory, never the source workspace.
  if [[ "$scratch_dir" == /tmp/team4-terraform-tests.* && -d "$scratch_dir" ]]; then
    rm -rf -- "$scratch_dir"
  fi
}
trap cleanup EXIT

# Copy tracked source files only. In particular, exclude tfvars, state, plans,
# credentials and .terraform backend metadata. Working-tree edits are included.
while IFS= read -r -d '' relative_path; do
  mkdir -p "$scratch_dir/$(dirname "$relative_path")"
  cp -- "$repo_dir/$relative_path" "$scratch_dir/$relative_path"
done < <(git -c safe.directory="$repo_dir" -C "$repo_dir" ls-files -z -- \
  'infra/*.tf' 'infra/.terraform.lock.hcl' 'infra/tests/*.tftest.hcl')
test -f "$scratch_dir/infra/variables.tf"
test -f "$scratch_dir/infra/.terraform.lock.hcl"
test -f "$scratch_dir/infra/tests/safety.tftest.hcl"

# Preserve archive_file's relative source layout with an explicit code allowlist.
mkdir -p "$scratch_dir/automation"
for source_file in common.py sg_healing.py inspector_response.py; do
  cp -- "$repo_dir/automation/$source_file" "$scratch_dir/automation/$source_file"
done

# Reuse only installed provider executables, with an isolated data directory.
# Run `terraform -chdir=infra init -backend=false -lockfile=readonly` first.
source_data_dir="${TF_DATA_DIR:-$repo_dir/infra/.terraform}"
if [[ "$source_data_dir" != /* ]]; then
  source_data_dir="$repo_dir/infra/$source_data_dir"
fi
test -d "$source_data_dir/providers"
mkdir -p "$scratch_dir/infra/.terraform"
ln -s -- "$source_data_dir/providers" "$scratch_dir/infra/.terraform/providers"

# Environment variable defaults and injected CLI flags must not change the test.
for variable_name in ${!TF_VAR_@} ${!TF_CLI_ARGS@}; do
  unset "$variable_name"
done
unset TF_WORKSPACE TF_LOG TF_LOG_PATH
export TF_DATA_DIR="$scratch_dir/infra/.terraform"
terraform -chdir="$scratch_dir/infra" init -backend=false -input=false -lockfile=readonly -no-color
terraform -chdir="$scratch_dir/infra" test -no-color
