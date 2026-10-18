#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/lib-k8s.sh
require_demo_context kind-team4
: "${GITOPS_REVISION:?Set the full published Git commit to mirror}"
[[ "$GITOPS_REVISION" =~ ^[a-f0-9]{40}$ ]]
git -c "safe.directory=$PWD" cat-file -e "${GITOPS_REVISION}^{commit}"
mkdir -p generated evidence
bundle_dir="$(mktemp -d "$PWD/generated/gitops-mirror.XXXXXX")"
mirror="$bundle_dir/repo.git"
git init --bare "$mirror" >/dev/null
# Include complete reachable history: dumb HTTP cannot advertise shallow roots.
# Exact SHA fetch avoids accidentally serving uncommitted edits or another branch.
git -c "safe.directory=$PWD" -c "safe.directory=$mirror" --git-dir="$mirror" fetch --no-tags "$PWD" "$GITOPS_REVISION"
git -c "safe.directory=$mirror" --git-dir="$mirror" update-ref refs/heads/approved "$GITOPS_REVISION"
git -c "safe.directory=$mirror" --git-dir="$mirror" symbolic-ref HEAD refs/heads/approved
git -c "safe.directory=$mirror" --git-dir="$mirror" repack -a -d
git -c "safe.directory=$mirror" --git-dir="$mirror" update-server-info
actual="$(git -c "safe.directory=$mirror" --git-dir="$mirror" rev-parse refs/heads/approved)"
[[ "$actual" == "$GITOPS_REVISION" ]]
git -c "safe.directory=$mirror" --git-dir="$mirror" fsck --full --no-reflogs
git -c "safe.directory=$mirror" --git-dir="$mirror" cat-file -e "$GITOPS_REVISION:policies/network/kustomization.yaml"
tar -czf "$bundle_dir/repo.tar.gz" -C "$bundle_dir" repo.git
bundle_bytes="$(wc -c < "$bundle_dir/repo.tar.gz")"
# Headroom below the 1 MiB ConfigMap limit; never silently truncate source data.
(( bundle_bytes <= 900000 )) || { echo "BLOCKED: mirror archive is $bundle_bytes bytes; ConfigMap ceiling is 900000." >&2; exit 1; }
bundle_hash="$(sha256sum "$bundle_dir/repo.tar.gz" | cut -d' ' -f1)"
export MIRROR_CONFIGMAP="team4-git-mirror-${GITOPS_REVISION:0:12}-${bundle_hash:0:8}"
export MIRROR_IMAGE="${MIRROR_IMAGE:-$("${k[@]}" -n demo get deployment server -o jsonpath='{.spec.template.spec.containers[0].image}')}"
export GITOPS_REVISION
"${k[@]}" -n argocd create configmap "$MIRROR_CONFIGMAP" --from-file="repo.tar.gz=$bundle_dir/repo.tar.gz" --dry-run=client -o json |
  python3 -c 'import json,sys; obj=json.load(sys.stdin); obj["immutable"]=True; print(json.dumps(obj))' |
  "${k[@]}" apply --server-side --field-manager=team4-local-mirror -f -
python3 scripts/render-template.py k8s/gitops/local-mirror.yaml.template | "${k[@]}" apply -f -
"${k[@]}" -n argocd rollout status deployment/team4-git-mirror --timeout=180s
export GITOPS_REPO_URL=http://team4-git-mirror.argocd.svc.cluster.local:8080/repo.git
# Validate actual HTTP Git reads from the only permitted client workload.
mirror_ready=false
for attempt in {1..15}; do
  if remote_refs="$("${k[@]}" -n argocd exec deployment/argocd-repo-server -- git ls-remote "$GITOPS_REPO_URL" refs/heads/approved)" &&
      [[ "$remote_refs" == "$GITOPS_REVISION"$'\trefs/heads/approved' ]]; then
    mirror_ready=true; break
  fi
  sleep 2
done
[[ "$mirror_ready" == true ]] || { echo 'FAIL: repo-server HTTP refs did not match the required commit' >&2; exit 1; }
python3 - "$GITOPS_REVISION" "$bundle_hash" "$bundle_bytes" "$GITOPS_REPO_URL" > evidence/gitops-local-mirror.json <<'PY'
import json,sys
from datetime import datetime,timezone
print(json.dumps({"result":"PASS", "scope":"local-readonly-mirror", "source_commit":sys.argv[1],
                  "archive_sha256":sys.argv[2], "archive_bytes":int(sys.argv[3]), "url":sys.argv[4],
                  "checked_at":datetime.now(timezone.utc).isoformat(),
                  "direct_github_integration":"BLOCKED: repository disables deploy keys"}, indent=2))
PY
printf 'PASS: exact local Git mirror HTTP refs match %s\n' "$GITOPS_REVISION"
printf 'Next: export GITOPS_REPO_URL=%s\n' "$GITOPS_REPO_URL"
printf 'Then: bash scripts/11-gitops-drift-test.sh kind-team4\n'
