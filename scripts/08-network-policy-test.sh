#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/lib-k8s.sh
require_demo_context "${1:?Usage: bash scripts/08-network-policy-test.sh CONTEXT [--verify-only]}"
mkdir -p evidence
log_suffix=""
if [[ "${2:-}" == --verify-only ]]; then log_suffix=-verify-only; fi
exec > >(tee "evidence/network-${context}${log_suffix}.log") 2>&1
printf 'Started UTC: %s\n' "$(date -u +%FT%TZ)"
for app in server client unauthorized; do
  "${k[@]}" -n demo rollout status "deployment/$app" --timeout=180s
done
if [[ "${2:-}" != --verify-only ]]; then "${k[@]}" apply -k policies/network; fi
ip="$("${k[@]}" -n demo get service server -o jsonpath='{.spec.clusterIP}')"
url="http://${ip}:8080"
for app in client unauthorized; do
  dns_ready=false
  for attempt in {1..15}; do
    if "${k[@]}" -n demo exec "deployment/$app" -- nslookup server.demo.svc.cluster.local >/dev/null 2>&1; then
      dns_ready=true; break
    fi
    sleep 2
  done
  [[ "$dns_ready" == true ]] || { echo "FAIL: $app DNS did not converge" >&2; exit 1; }
done
wait_http client "$url"
expect_blocked unauthorized "$url"
if [[ "${2:-}" == --verify-only ]]; then
  echo 'PASS: DNS, allowed client, denied unauthorized traffic (no policy mutations).'
  exit 0
fi
# Separate ingress and egress causality using narrow temporary grants.
# The temporary policies never enter the Argo CD source directory.
cleanup() { "${k[@]}" -n demo delete networkpolicy test-allow-unauthorized-ingress test-allow-unauthorized-egress --ignore-not-found >/dev/null; }
trap cleanup EXIT
"${k[@]}" apply -f - <<'YAML'
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata: {name: test-allow-unauthorized-ingress, namespace: demo}
spec:
  podSelector: {matchLabels: {app: server}}
  policyTypes: [Ingress]
  ingress:
    - from: [{podSelector: {matchLabels: {app: unauthorized}}}]
      ports: [{protocol: TCP, port: 8080}]
YAML
expect_blocked unauthorized "$url"
echo 'PASS: Egress independently blocks unauthorized traffic while ingress permits it.'
"${k[@]}" apply -f - <<'YAML'
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata: {name: test-allow-unauthorized-egress, namespace: demo}
spec:
  podSelector: {matchLabels: {app: unauthorized}}
  policyTypes: [Egress]
  egress:
    - to: [{podSelector: {matchLabels: {app: server}}}]
      ports: [{protocol: TCP, port: 8080}]
YAML
wait_http unauthorized "$url"
echo 'PASS: Same source and destination connect when both directions permit them.'
"${k[@]}" -n demo delete networkpolicy test-allow-unauthorized-ingress
expect_blocked unauthorized "$url"
echo 'PASS: Ingress independently blocks unauthorized traffic while egress permits it.'
cleanup
trap - EXIT
expect_blocked unauthorized "$url"
"${k[@]}" -n demo get networkpolicy -o json > "evidence/network-${context}.json"
printf 'PASS: NetworkPolicy enforcement; completed UTC: %s\n' "$(date -u +%FT%TZ)"
