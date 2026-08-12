#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

mapfile -t gates < <(bash infra/scripts/nur-gate.sh --list)
[[ "${#gates[@]}" -eq 17 ]]
[[ "${gates[0]}" == "G00_EVIDENCE" ]]
[[ "${gates[16]}" == "G16_FULL_RELEASE" ]]

set +e
output="$(bash infra/scripts/nur-gate.sh G99_NOT_REAL 2>&1)"
status=$?
set -e
[[ "$status" -eq 2 ]]
[[ "$output" == *"Unknown NUR gate"* ]]

printf 'nur-gate contract: PASS (%s gates)\n' "${#gates[@]}"
