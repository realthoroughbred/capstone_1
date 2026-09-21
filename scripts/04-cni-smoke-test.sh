#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
context="${1:?Usage: bash scripts/04-cni-smoke-test.sh kind-team4}"
k=(kubectl --context "$context" -n demo)
if [[ "$context" != kind-team4 && "$context" != team4-eks ]]; then
  echo 'Only kind-team4 or team4-eks is accepted.' >&2
  exit 1
fi
"${k[@]}" exec deployment/client -- wget -T 5 -qO- http://server:8080
"${k[@]}" exec deployment/unauthorized -- wget -T 5 -qO- http://server:8080
"${k[@]}" apply -f policies/smoke-server-ingress.yaml
trap '"${k[@]}" delete -f policies/smoke-server-ingress.yaml --ignore-not-found' EXIT
server_ip="$("${k[@]}" get service server -o jsonpath='{.spec.clusterIP}')"
blocked=false
for attempt in 1 2 3 4 5 6; do
  # Use the same destination IP, avoiding a DNS failure being mistaken for policy enforcement.
  "${k[@]}" exec deployment/client -- wget -T 5 -qO- "http://${server_ip}:8080"
  if "${k[@]}" exec deployment/unauthorized -- wget -T 5 -qO- "http://${server_ip}:8080"; then
    sleep 2
  else
    "${k[@]}" exec deployment/unauthorized -- true
    "${k[@]}" exec deployment/client -- wget -T 5 -qO- "http://${server_ip}:8080"
    blocked=true
    break
  fi
done
if [[ "$blocked" != true ]]; then
  echo 'FAIL: unauthorized connection was not blocked.' >&2
  exit 1
fi
"${k[@]}" delete -f policies/smoke-server-ingress.yaml
trap - EXIT
for attempt in 1 2 3 4 5 6; do
  if "${k[@]}" exec deployment/unauthorized -- wget -T 5 -qO- "http://${server_ip}:8080"; then
    echo 'PASS: baseline allowed, policy blocked only unauthorized, removal restored connection.'
    exit 0
  fi
  sleep 2
done
echo 'FAIL: connection did not recover after policy removal.' >&2
exit 1
