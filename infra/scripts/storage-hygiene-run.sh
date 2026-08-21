#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
API_DIR="$ROOT_DIR/apps/api"
PYTHON_BIN="${NUR_STORAGE_HYGIENE_PYTHON:-$API_DIR/.venv/bin/python}"
OBJECT_ROOT="${NUR_STORAGE_HYGIENE_OBJECT_ROOT:-}"
DELETE_ORPHANS="${NUR_STORAGE_HYGIENE_DELETE_ORPHANS:-false}"
RETENTION_SECONDS="${NUR_STORAGE_HYGIENE_RETENTION_SECONDS:-604800}"
LOCK_FILE="${NUR_STORAGE_HYGIENE_LOCK_FILE:-$ROOT_DIR/.nur-runtime/storage-hygiene.lock}"

if [[ -z "${NUR_STORAGE_HYGIENE_DATABASE_URL:-}" ]]; then
  echo "NUR_STORAGE_HYGIENE_DATABASE_URL is required" >&2
  exit 64
fi
if [[ -z "$OBJECT_ROOT" ]]; then
  echo "NUR_STORAGE_HYGIENE_OBJECT_ROOT is required" >&2
  exit 64
fi
if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "storage hygiene Python is not executable: $PYTHON_BIN" >&2
  exit 69
fi
if [[ ! "$RETENTION_SECONDS" =~ ^[0-9]+$ ]]; then
  echo "NUR_STORAGE_HYGIENE_RETENTION_SECONDS must be a non-negative integer" >&2
  exit 64
fi

mkdir -p -- "$(dirname -- "$LOCK_FILE")"
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo "storage hygiene already running; singleton lock held" >&2
  exit 0
fi

args=(
  -m app.services.storage_hygiene reconcile
  --object-root "$OBJECT_ROOT"
  --deleted-retention-seconds "$RETENTION_SECONDS"
)
case "${DELETE_ORPHANS,,}" in
  1|true|yes|on) args+=(--delete) ;;
  0|false|no|off) ;;
  *)
    echo "NUR_STORAGE_HYGIENE_DELETE_ORPHANS must be true or false" >&2
    exit 64
    ;;
esac

cd -- "$API_DIR"
exec "$PYTHON_BIN" "${args[@]}"
