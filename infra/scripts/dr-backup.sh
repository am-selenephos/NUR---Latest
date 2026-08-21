#!/usr/bin/env bash
# Full disaster-recovery backup: Postgres database + local object store + a
# verified manifest (applied Alembic revision, dump digest, per-object digests).
#
# Usage:
#   NUR_DR_DATABASE_URL=postgresql://user:pass@host:port/db \
#   NUR_DR_OBJECT_ROOT=/path/to/project-objects \
#   dr-backup.sh <backup-dir>
#
# The database URL should be a role that can read every row (a superuser or the
# schema owner); RLS-restricted roles produce an incomplete dump.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BACKUP_DIR="${1:?Usage: dr-backup.sh <backup-dir>}"
DB_URL="${NUR_DR_DATABASE_URL:-${DATABASE_URL:-}}"
OBJECT_ROOT="${NUR_DR_OBJECT_ROOT:-$ROOT/.nur-runtime/project-objects}"
PYTHON="${NUR_DR_PYTHON:-$ROOT/apps/api/.venv/bin/python}"
SOURCE_OBJECTS_BEFORE=""
SOURCE_OBJECTS_AFTER=""
COPIED_OBJECTS=""

cleanup() {
  [[ -z "$SOURCE_OBJECTS_BEFORE" ]] || rm -f -- "$SOURCE_OBJECTS_BEFORE"
  [[ -z "$SOURCE_OBJECTS_AFTER" ]] || rm -f -- "$SOURCE_OBJECTS_AFTER"
  [[ -z "$COPIED_OBJECTS" ]] || rm -f -- "$COPIED_OBJECTS"
}
trap cleanup EXIT

object_fingerprint() {
  local root="$1"
  local output="$2"
  : > "$output"
  [[ -d "$root" ]] || return 0
  while IFS= read -r -d '' relative; do
    printf '%s  %s\n' "$(sha256sum "$root/$relative" | awk '{print $1}')" "$relative" \
      >> "$output"
  done < <(find "$root" -type f -printf '%P\0' | sort -z)
}

if [[ -z "$DB_URL" ]]; then
  printf "Set NUR_DR_DATABASE_URL (or DATABASE_URL) before backup.\n" >&2
  exit 2
fi
if [[ ! -x "$PYTHON" ]]; then
  printf "DR Python is unavailable: %s\n" "$PYTHON" >&2
  exit 2
fi
DB_URL="${DB_URL/postgresql+asyncpg:/postgresql:}"

if [[ -e "$BACKUP_DIR" ]]; then
  if [[ ! -d "$BACKUP_DIR" || -n "$(find "$BACKUP_DIR" -mindepth 1 -maxdepth 1 -print -quit)" ]]; then
    printf "Backup destination must be an empty new directory: %s\n" "$BACKUP_DIR" >&2
    exit 2
  fi
else
  mkdir -p "$BACKUP_DIR"
fi
chmod 700 "$BACKUP_DIR"
DUMP="$BACKUP_DIR/db.dump"
OBJ_OUT="$BACKUP_DIR/objects"
SOURCE_OBJECTS_BEFORE="$(mktemp)"
SOURCE_OBJECTS_AFTER="$(mktemp)"
COPIED_OBJECTS="$(mktemp)"
object_fingerprint "$OBJECT_ROOT" "$SOURCE_OBJECTS_BEFORE"

# 1. Database — custom format with ownership and ACLs intact. Security-definer
# ownership and runtime grants are part of the security boundary, not metadata
# that a restore may silently replace.
pg_dump --format=custom --file "$DUMP" "$DB_URL"

# 2. Applied migration revision. A canonical NUR backup without a readable
# revision is not restorable evidence, so lookup errors are fatal.
REVISION="$(
  psql "$DB_URL" -v ON_ERROR_STOP=1 -tAc "SELECT version_num FROM alembic_version" \
    | head -n1 | tr -d '[:space:]'
)"
[[ -n "$REVISION" ]] || { printf "Database has no applied Alembic revision.\n" >&2; exit 1; }

# 3. Object store — copy the tree faithfully (preserve structure; skip if empty).
mkdir -p "$OBJ_OUT"
if [[ -d "$OBJECT_ROOT" ]]; then
  # -a preserves the layout; the trailing dot copies contents, not the dir.
  cp -a "$OBJECT_ROOT/." "$OBJ_OUT/"
elif [[ -e "$OBJECT_ROOT" ]]; then
  printf "Object root exists but is not a directory: %s\n" "$OBJECT_ROOT" >&2
  exit 1
fi

object_fingerprint "$OBJECT_ROOT" "$SOURCE_OBJECTS_AFTER"
object_fingerprint "$OBJ_OUT" "$COPIED_OBJECTS"
if ! cmp -s "$SOURCE_OBJECTS_BEFORE" "$SOURCE_OBJECTS_AFTER"; then
  printf "Object store changed during backup; refusing a split DB/object snapshot.\n" >&2
  exit 1
fi
if ! cmp -s "$SOURCE_OBJECTS_AFTER" "$COPIED_OBJECTS"; then
  printf "Copied object tree does not match the stable source tree.\n" >&2
  exit 1
fi

# 4. Manifest — the integrity contract (Python owns it; unit-tested).
"$PYTHON" -m app.services.dr build \
  --db-dump "$DUMP" \
  --object-root "$OBJ_OUT" \
  --alembic-revision "$REVISION" \
  --out "$BACKUP_DIR/manifest.json"

sha256sum "$BACKUP_DIR/manifest.json" > "$BACKUP_DIR/manifest.json.sha256"
printf "%s\n" "$BACKUP_DIR"
