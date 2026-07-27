#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

# Build the forbidden token at runtime so the scanner does not contain the
# literal string it is responsible for rejecting.
forbidden_token="$(printf '%s%s' 'cou' 'sin')"
status=0

path_hits="$(git ls-files | grep -i -- "$forbidden_token" || true)"
if [[ -n "$path_hits" ]]; then
  printf 'FORBIDDEN TOKEN IN TRACKED PATHS:\n%s\n\n' "$path_hits" >&2
  status=1
fi

content_hits="$(git grep -nIi -- "$forbidden_token" -- . || true)"
if [[ -n "$content_hits" ]]; then
  printf 'FORBIDDEN TOKEN IN TRACKED FILE CONTENT:\n%s\n\n' "$content_hits" >&2
  status=1
fi

if [[ "$status" -ne 0 ]]; then
  printf 'repo naming scan: FAIL — remove every tracked path/content occurrence.\n' >&2
  exit 1
fi

printf 'repo naming scan: PASS — no tracked path or text file contains the forbidden token.\n'
