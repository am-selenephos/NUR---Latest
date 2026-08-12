#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

for script in infra/scripts/package-release.sh infra/scripts/verify-release-package.sh; do
  bash -n "$script"
done

set +e
invalid="$(bash infra/scripts/package-release.sh --verdict NOT_A_VERDICT 2>&1)"
status=$?
set -e
[[ "$status" -eq 2 ]]
[[ "$invalid" == *"Invalid release verdict"* ]]

set +e
missing="$(bash infra/scripts/verify-release-package.sh /does/not/exist.zip 2>&1)"
status=$?
set -e
[[ "$status" -eq 2 ]]
[[ "$missing" == *"Usage:"* ]]

printf 'release-package contract: PASS\n'
