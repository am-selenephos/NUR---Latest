#!/usr/bin/env bash
# Restore a dr-backup into an ISOLATED target and verify it byte-for-byte before
# declaring success. Fails closed: a wrong revision, a missing/corrupted/extra
# object, or a tampered dump makes this exit non-zero.
#
# Usage:
#   NUR_DR_RESTORE_DATABASE_URL=postgresql://user:pass@host:port/isolated_db \
#   NUR_DR_RESTORE_OBJECT_ROOT=/path/to/isolated/object-root \
#   dr-restore.sh <backup-dir>
#
# The target database and object root MUST be isolated (not production): restore
# is destructive to them (--clean).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BACKUP_DIR="${1:?Usage: dr-restore.sh <backup-dir>}"
DB_URL="${NUR_DR_RESTORE_DATABASE_URL:-}"
OBJECT_ROOT="${NUR_DR_RESTORE_OBJECT_ROOT:-}"
CONFIRM_DATABASE="${NUR_DR_RESTORE_CONFIRM_DATABASE:-}"
CONFIRM_OBJECT_ROOT="${NUR_DR_RESTORE_CONFIRM_OBJECT_ROOT:-}"
PYTHON="${NUR_DR_PYTHON:-$ROOT/apps/api/.venv/bin/python}"

if [[ -z "$DB_URL" || -z "$OBJECT_ROOT" ]]; then
  printf "Set NUR_DR_RESTORE_DATABASE_URL and NUR_DR_RESTORE_OBJECT_ROOT.\n" >&2
  exit 2
fi
if [[ ! -x "$PYTHON" ]]; then
  printf "DR Python is unavailable: %s\n" "$PYTHON" >&2
  exit 2
fi
DB_URL="${DB_URL/postgresql+asyncpg:/postgresql:}"
OBJECT_ROOT="$(realpath -m "$OBJECT_ROOT")"
CONFIRM_OBJECT_ROOT="$(realpath -m "${CONFIRM_OBJECT_ROOT:-/}")"
DB_NAME="${DB_URL%%\?*}"
DB_NAME="${DB_NAME##*/}"
if [[ -z "$DB_NAME" || "$DB_NAME" == "postgres" || "$DB_NAME" == template* ]]; then
  printf "Refusing unsafe restore database target: %s\n" "${DB_NAME:-<empty>}" >&2
  exit 2
fi
if [[ "$CONFIRM_DATABASE" != "$DB_NAME" || "$CONFIRM_OBJECT_ROOT" != "$OBJECT_ROOT" ]]; then
  printf "Restore confirmation does not exactly match database and object targets.\n" >&2
  exit 2
fi
if [[ "$OBJECT_ROOT" == "/" || "$OBJECT_ROOT" == "$HOME" ]]; then
  printf "Refusing to restore objects into filesystem root or home.\n" >&2
  exit 2
fi

DUMP="$BACKUP_DIR/db.dump"
MANIFEST="$BACKUP_DIR/manifest.json"
OBJ_SRC="$BACKUP_DIR/objects"
for required in "$DUMP" "$MANIFEST" "$MANIFEST.sha256"; do
  [[ -f "$required" ]] || { printf "Backup incomplete: missing %s\n" "$required" >&2; exit 2; }
done
[[ -d "$OBJ_SRC" ]] || { printf "Backup incomplete: missing %s\n" "$OBJ_SRC" >&2; exit 2; }

# 0. Verify the archive before touching the isolated target. A corrupt dump or
# partial object copy must fail before the database is destructively restored.
( cd "$BACKUP_DIR" && sha256sum -c manifest.json.sha256 >/dev/null ) \
  || { printf "Manifest checksum does not match - refusing restore.\n" >&2; exit 1; }
MANIFEST_REVISION="$("$PYTHON" -c \
  'import json,sys; print(json.load(open(sys.argv[1]))["alembic_revision"])' \
  "$MANIFEST")"
"$PYTHON" -m app.services.dr verify \
  --manifest "$MANIFEST" \
  --object-root "$OBJ_SRC" \
  --alembic-revision "$MANIFEST_REVISION" \
  --db-dump "$DUMP"

# Stage and verify object bytes before changing either restored state surface.
OBJECT_PARENT="$(dirname "$OBJECT_ROOT")"
mkdir -p "$OBJECT_PARENT"
OBJ_STAGE="$(mktemp -d "$OBJECT_PARENT/.nur-dr-objects.XXXXXX")"
TMP_SQL=""
cleanup() {
  [[ -z "$TMP_SQL" ]] || rm -f "$TMP_SQL"
  [[ -z "$OBJ_STAGE" ]] || rm -rf -- "$OBJ_STAGE"
}
trap cleanup EXIT
cp -a "$OBJ_SRC/." "$OBJ_STAGE/"
"$PYTHON" -m app.services.dr verify \
  --manifest "$MANIFEST" \
  --object-root "$OBJ_STAGE" \
  --alembic-revision "$MANIFEST_REVISION" \
  --db-dump "$DUMP"

# 1. Database — restore into the isolated target.
TMP_SQL="$(mktemp)"
pg_restore --clean --if-exists --file "$TMP_SQL" "$DUMP"
# Strip a GUC newer pg_dump clients emit that older local servers reject; it is
# not schema or data state.
sed -i '/^SET transaction_timeout =/d' "$TMP_SQL"
psql "$DB_URL" -v ON_ERROR_STOP=1 -q -f "$TMP_SQL"
ACTUAL_DATABASE="$(psql "$DB_URL" -v ON_ERROR_STOP=1 -tAc "SELECT current_database()" | tr -d '[:space:]')"
if [[ "$ACTUAL_DATABASE" != "$CONFIRM_DATABASE" ]]; then
  printf "Connected restore database does not match confirmation.\n" >&2
  exit 1
fi

# 2. Verify the database revision against the already verified staged objects.
RESTORED_REVISION="$(
  psql "$DB_URL" -v ON_ERROR_STOP=1 -tAc "SELECT version_num FROM alembic_version" \
    | head -n1 | tr -d '[:space:]'
)"
[[ -n "$RESTORED_REVISION" ]] || {
  printf "Restored database has no applied Alembic revision.\n" >&2
  exit 1
}

"$PYTHON" -m app.services.dr verify \
  --manifest "$MANIFEST" \
  --object-root "$OBJ_STAGE" \
  --alembic-revision "$RESTORED_REVISION" \
  --db-dump "$DUMP"

# 3. Publish the verified object tree only after database restore verification.
rm -rf -- "$OBJECT_ROOT"
mv "$OBJ_STAGE" "$OBJECT_ROOT"
OBJ_STAGE=""
"$PYTHON" -m app.services.dr verify \
  --manifest "$MANIFEST" \
  --object-root "$OBJECT_ROOT" \
  --alembic-revision "$RESTORED_REVISION" \
  --db-dump "$DUMP"
