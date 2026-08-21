#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

output="$(
  cd "$ROOT"
  APP_ENV=production API_ORIGIN=https://nur.invalid \
    bash infra/scripts/seed-demo-nur.sh 2>&1
)" && {
  printf 'seed-demo-nur.sh unexpectedly accepted APP_ENV=production\n' >&2
  exit 1
}

grep -Fq 'refuses to run when APP_ENV=production' <<<"$output"
printf 'Demo seed production guard: PASS\n'
