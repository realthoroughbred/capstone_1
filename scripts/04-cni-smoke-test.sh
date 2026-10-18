#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
# Compatibility entrypoint: final deny-by-default policies remain installed.
exec bash scripts/08-network-policy-test.sh "${1:?Usage: bash scripts/04-cni-smoke-test.sh CONTEXT}"
