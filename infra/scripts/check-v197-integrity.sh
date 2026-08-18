#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

cd "$ROOT"
if [[ -x "$ROOT/node_modules/.bin/tsc" ]]; then
  "$ROOT/node_modules/.bin/tsc" \
    scripts/check-v197-integrity.ts \
    --target ES2022 \
    --module NodeNext \
    --moduleResolution NodeNext \
    --skipLibCheck \
    --outDir "$TMP"
  node "$TMP/check-v197-integrity.js"
else
  # HOLD/fresh-extract packages intentionally omit node_modules. Node 22 can
  # execute this isolated type-annotated checker without installing dependencies.
  node --experimental-strip-types scripts/check-v197-integrity.ts
fi
