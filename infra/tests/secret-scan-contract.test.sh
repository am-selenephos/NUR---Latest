#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PROBE_DIR="$ROOT/evidence/secret-scan-contract"
PROBE="$PROBE_DIR/runtime.log"

cleanup() {
  rm -rf "$PROBE_DIR"
}
trap cleanup EXIT
mkdir -p "$PROBE_DIR"

# Assemble the probe at runtime so the test source never contains a credential
# pattern that the scanner should (correctly) reject.
printf '%s%s%s%s\n' 'OPENAI' '_API_KEY=' 's' 'k-proj-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa' >"$PROBE"

if output="$(cd "$ROOT" && bash infra/scripts/secret-scan.sh 2>&1)"; then
  printf 'secret scan unexpectedly accepted a generated credential artifact\n' >&2
  exit 1
fi

grep -Fq 'Secret scan failed in generated evidence artifacts.' <<<"$output"
printf 'Secret scan generated-artifact contract: PASS\n'
