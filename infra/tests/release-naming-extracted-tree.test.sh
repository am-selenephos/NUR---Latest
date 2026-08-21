#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

TREE="$TMP/NUR extracted tree"
mkdir -p "$TREE/infra/scripts" "$TREE/apps/web/src"
cp "$ROOT/infra/scripts/release-naming-scan.sh" "$TREE/infra/scripts/"
cp "$ROOT/README.md" "$ROOT/package.json" "$ROOT/package-lock.json" "$TREE/"
printf 'public NUR surface\n' > "$TREE/apps/web/src/surface.txt"

(cd "$TREE" && bash infra/scripts/release-naming-scan.sh) >/dev/null

forbidden_token="$(printf '%s%s' 'cou' 'sin')"
printf '%s\n' "$forbidden_token" > "$TREE/apps/web/src/forbidden.txt"
set +e
bad_output="$(cd "$TREE" && bash infra/scripts/release-naming-scan.sh 2>&1)"
bad_status=$?
set -e
[[ "$bad_status" -eq 1 ]]
[[ "$bad_output" == *"FORBIDDEN TOKEN"* ]]

EMPTY="$TMP/incomplete extracted tree"
mkdir -p "$EMPTY/infra/scripts"
cp "$ROOT/infra/scripts/release-naming-scan.sh" "$EMPTY/infra/scripts/"
set +e
empty_output="$(cd "$EMPTY" && bash infra/scripts/release-naming-scan.sh 2>&1)"
empty_status=$?
set -e
[[ "$empty_status" -ne 0 ]]
[[ "$empty_output" == *"cannot establish release root"* ]]

printf 'release naming extracted tree: PASS\n'
