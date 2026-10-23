#!/usr/bin/env bash
set -euo pipefail
set +x
cd "$(dirname "$0")/.."
source scripts/lib-k8s.sh
require_demo_context "${1:?Usage: 09-eso-test.sh CONTEXT fake|aws [--rotate-demo]}"
mode="${2:?fake or aws required}"
mkdir -p evidence
exec > >(tee "evidence/eso-${context}.log") 2>&1
printf 'Started UTC: %s, provider=%s\n' "$(date -u +%FT%TZ)" "$mode"
if [[ "$mode" == fake ]]; then
  [[ "$context" == kind-team4 ]] || { echo 'Fake provider is local only'; exit 1; }
  "${k[@]}" apply -f k8s/eso/fake.yaml
elif [[ "$mode" == aws ]]; then
  [[ "$context" == team4-eks ]] || exit 1
  : "${ESO_ROLE_ARN:?}" "${DEMO_SECRET_ARN:?}" "${AWS_REGION:=ap-northeast-2}"
  export ESO_ROLE_ARN DEMO_SECRET_ARN AWS_REGION
  python3 scripts/render-template.py k8s/eso/aws.yaml.template | "${k[@]}" apply -f -
else
  echo 'Expected fake or aws' >&2; exit 1
fi
"${k[@]}" -n demo wait --for=condition=Ready externalsecret/team4-eso-demo --timeout=180s
export TEST_IMAGE="$("${k[@]}" -n demo get deployment server -o jsonpath='{.spec.template.spec.containers[0].image}')"
python3 scripts/render-template.py k8s/eso/consumer.yaml.template | "${k[@]}" apply -f -
"${k[@]}" -n demo rollout status deployment/secret-reader --timeout=180s
secret_hash() { "${k[@]}" -n demo get secret team4-eso-demo -o jsonpath='{.data.token}' | base64 --decode | sha256sum | cut -d' ' -f1; }
pod_hash() { "${k[@]}" -n demo exec deployment/secret-reader -- sha256sum /var/run/demo-secret/token | cut -d' ' -f1; }
before="$(secret_hash)"
[[ "$before" == "$(pod_hash)" ]]
echo 'PASS: ESO reconciled Secret and Pod mounted identical token (value omitted).'
if [[ "$mode" == aws && "${3:-}" != --rotate-demo ]]; then
  echo 'NOT_TESTED: AWS rotation; explicitly pass --rotate-demo for this dedicated test secret.'
  exit 0
fi
if [[ "$mode" == fake ]]; then
  python3 -c 'import json,secrets; print(json.dumps({"spec":{"provider":{"fake":{"data":[{"key":"/team4/demo/token","value":secrets.token_hex(32)}]}}}}))' |
    "${k[@]}" -n demo patch secretstore team4-fake --type merge --patch-file /dev/stdin >/dev/null
else
  # Restrict mutation to the secret recorded in this workspace's Terraform state.
  [[ "$DEMO_SECRET_ARN" == "$(terraform -chdir=infra output -raw demo_secret_arn)" ]]
  [[ "$(aws sts get-caller-identity --query Account --output text)" == "$(cut -d: -f5 <<< "$DEMO_SECRET_ARN")" ]]
  secret_file="$(mktemp)"; chmod 600 "$secret_file"
  trap 'rm -f "$secret_file"' EXIT
  python3 -c 'import json,secrets; print(json.dumps({"token":secrets.token_hex(32)}))' > "$secret_file"
  aws secretsmanager put-secret-value --region "$AWS_REGION" --secret-id "$DEMO_SECRET_ARN" --secret-string "file://$secret_file" --query VersionId --output text >/dev/null
  rm -f "$secret_file"; trap - EXIT
fi
"${k[@]}" -n demo annotate externalsecret team4-eso-demo "force-sync=$(date +%s)" --overwrite >/dev/null
for attempt in {1..90}; do
  after="$(secret_hash)"
  if [[ "$after" != "$before" && "$after" == "$(pod_hash)" ]]; then
    echo 'PASS: Rotation reached Kubernetes Secret AND running Pod volume without restart.'
    "${k[@]}" -n demo get externalsecret team4-eso-demo -o json > "evidence/eso-${context}.json"
    exit 0
  fi
  sleep 2
done
echo 'FAIL: Secret/Pod rotation did not converge in 180s' >&2
exit 1
