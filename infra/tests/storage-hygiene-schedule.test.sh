#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
RUNNER="$ROOT_DIR/infra/scripts/storage-hygiene-run.sh"
SERVICE="$ROOT_DIR/infra/systemd/nur-storage-hygiene.service"
TIMER="$ROOT_DIR/infra/systemd/nur-storage-hygiene.timer"

test -x "$RUNNER"
test -f "$SERVICE"
test -f "$TIMER"

grep -q 'NUR_STORAGE_HYGIENE_DATABASE_URL' "$RUNNER"
grep -q 'NUR_STORAGE_HYGIENE_OBJECT_ROOT' "$RUNNER"
grep -q 'NUR_STORAGE_HYGIENE_DELETE_ORPHANS' "$RUNNER"
grep -q -- '--delete' "$RUNNER"
grep -q 'Persistent=true' "$TIMER"
grep -q 'RandomizedDelaySec=' "$TIMER"
grep -q 'NoNewPrivileges=true' "$SERVICE"
grep -q 'ProtectSystem=strict' "$SERVICE"

if env -u NUR_STORAGE_HYGIENE_DATABASE_URL \
  NUR_STORAGE_HYGIENE_OBJECT_ROOT=/tmp/nur-storage-test \
  "$RUNNER" >/tmp/nur-storage-hygiene-test.out 2>&1; then
  echo "runner accepted a missing maintenance DSN" >&2
  exit 1
fi
grep -q 'NUR_STORAGE_HYGIENE_DATABASE_URL is required' /tmp/nur-storage-hygiene-test.out

echo "storage hygiene schedule contract PASS"
