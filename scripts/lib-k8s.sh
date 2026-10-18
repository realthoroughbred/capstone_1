#!/usr/bin/env bash
# Source after cd to repository root. Never mutate an implicit current context.
require_demo_context() {
  context="${1:?Explicit context required (kind-team4 or team4-eks)}"
  case "$context" in kind-team4|team4-eks) ;; *) echo "Refusing context: $context" >&2; return 1 ;; esac
  k=(kubectl --context "$context")
  "${k[@]}" get namespace demo >/dev/null
  [[ "$("${k[@]}" get namespace demo -o jsonpath='{.metadata.labels.project}')" == team4 ]]
}
wait_http() {
  local app="$1" url="$2" tries="${3:-15}" attempt
  for ((attempt=0; attempt<tries; attempt++)); do
    if "${k[@]}" -n demo exec "deployment/$app" -- wget -T 3 -qO- "$url" >/dev/null 2>&1; then return 0; fi
    sleep 2
  done
  echo "FAIL: $app cannot reach $url" >&2
  return 1
}
expect_blocked() {
  local app="$1" url="$2" consecutive=0 attempt
  # A healthy exec and successful control request prevent transport/DNS errors
  # from counting as policy success. Require three blocked probes.
  for ((attempt=0; attempt<15; attempt++)); do
    "${k[@]}" -n demo exec "deployment/$app" -- true
    wait_http client "$url" 2 || return 1
    if "${k[@]}" -n demo exec "deployment/$app" -- wget -T 3 -qO- "$url" >/dev/null 2>&1; then
      consecutive=0
    else
      consecutive=$((consecutive + 1))
      if (( consecutive >= 3 )); then return 0; fi
    fi
    sleep 2
  done
  echo "FAIL: $app connection was allowed" >&2
  return 1
}
