#!/usr/bin/env bash
# A real disaster-recovery drill, fully isolated from production state:
#
#   1. seed an isolated object store with known content,
#   2. back up a real source database + that object store (dr-backup.sh),
#   3. provision a fresh isolated target database + object root,
#   4. restore into the target and verify byte-for-byte (dr-restore.sh),
#   5. compare every public table's row count + content digest, sequence state,
#      and RLS/policy fingerprint between source and restored target,
#   6. tear the target down.
#
# It never writes to the source database or to production object roots. Exit 0
# means a backup taken now can be restored and independently verified.
#
# Env (all have working defaults for a local dev cluster):
#   NUR_DR_SUPERUSER_DSN   base superuser DSN, no database (default local postgres)
#   NUR_DR_SOURCE_DB       database to back up (default: nur)
#   NUR_DR_TARGET_OWNER    owner role for the isolated restore db (default: nur_admin)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT/apps/api"  # so `python -m app.services.dr` resolves

SUP_DSN="${NUR_DR_SUPERUSER_DSN:-postgresql://postgres:postgres@localhost:5432}"
SOURCE_DB="${NUR_DR_SOURCE_DB:-nur}"
TARGET_OWNER="${NUR_DR_TARGET_OWNER:-nur_admin}"
RUNTIME_BASE_DSN="${NUR_DR_RUNTIME_BASE_DSN:-postgresql://nur_app:nur_app_pw@localhost:5432}"
TARGET_DB="nur_dr_drill_$$"

WORK="$(mktemp -d)"
cleanup() {
  psql "$SUP_DSN/postgres" -v ON_ERROR_STOP=0 -q \
    -c "DROP DATABASE IF EXISTS ${TARGET_DB} WITH (FORCE)" >/dev/null 2>&1 || true
  rm -rf "$WORK"
}
trap cleanup EXIT

now_ms() {
  date +%s%3N
}

database_fingerprint() {
  local dsn="$1"
  local output="$2"
  local qualified row_count content_sha sequence_state rls_line

  : > "$output"
  while IFS= read -r qualified; do
    [[ -n "$qualified" ]] || continue
    row_count="$(psql "$dsn" -v ON_ERROR_STOP=1 -tAc "SELECT count(*) FROM ${qualified}")"
    content_sha="$(
      psql "$dsn" -v ON_ERROR_STOP=1 -qAtc \
        "COPY (SELECT row_to_json(t)::text FROM ${qualified} AS t ORDER BY row_to_json(t)::text) TO STDOUT" \
        | sha256sum | awk '{print $1}'
    )"
    printf 'table\t%s\t%s\t%s\n' "$qualified" "$row_count" "$content_sha" >> "$output"
  done < <(
    psql "$dsn" -v ON_ERROR_STOP=1 -tAc \
      "SELECT format('%I.%I', schemaname, tablename) FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename"
  )

  while IFS= read -r qualified; do
    [[ -n "$qualified" ]] || continue
    sequence_state="$(
      psql "$dsn" -v ON_ERROR_STOP=1 -tAc \
        "SELECT last_value::text || ':' || is_called::text FROM ${qualified}"
    )"
    printf 'sequence\t%s\t%s\n' "$qualified" "$sequence_state" >> "$output"
  done < <(
    psql "$dsn" -v ON_ERROR_STOP=1 -tAc \
      "SELECT format('%I.%I', schemaname, sequencename) FROM pg_sequences WHERE schemaname = 'public' ORDER BY sequencename"
  )

  while IFS= read -r rls_line; do
    [[ -n "$rls_line" ]] || continue
    printf 'rls-policy\t%s\n' "$rls_line" >> "$output"
  done < <(
    psql "$dsn" -v ON_ERROR_STOP=1 -qAtc \
      "COPY (
         SELECT 'table' AS kind,
                c.relname AS identity,
                c.relrowsecurity::text AS setting,
                c.relforcerowsecurity::text || ':' || pg_get_userbyid(c.relowner) AS detail
           FROM pg_class AS c
           JOIN pg_namespace AS n ON n.oid = c.relnamespace
          WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p')
         UNION ALL
         SELECT 'policy',
                schemaname || '.' || tablename || '.' || policyname,
                permissive || ':' || roles::text || ':' || cmd,
                'using=' || regexp_replace(
                    regexp_replace(coalesce(qual, '<null>'),
                                   '::(character varying|text)(\\[\\])?', '', 'g'),
                    '[[:space:]()]', '', 'g') ||
                ':check=' || regexp_replace(
                    regexp_replace(coalesce(with_check, '<null>'),
                                   '::(character varying|text)(\\[\\])?', '', 'g'),
                    '[[:space:]()]', '', 'g')
           FROM pg_policies
          WHERE schemaname = 'public'
          ORDER BY 1, 2, 3, 4
       ) TO STDOUT" \
  )

  while IFS= read -r rls_line; do
    [[ -n "$rls_line" ]] || continue
    printf 'grant\t%s\n' "$rls_line" >> "$output"
  done < <(
    psql "$dsn" -v ON_ERROR_STOP=1 -qAtc \
      "COPY (
         SELECT table_schema, table_name, grantee, privilege_type, is_grantable
           FROM information_schema.role_table_grants
          WHERE table_schema = 'public'
          ORDER BY 1, 2, 3, 4, 5
       ) TO STDOUT"
  )

  while IFS= read -r rls_line; do
    [[ -n "$rls_line" ]] || continue
    printf 'function\t%s\n' "$rls_line" >> "$output"
  done < <(
    psql "$dsn" -v ON_ERROR_STOP=1 -qAtc \
      "COPY (
         SELECT n.nspname, p.proname, pg_get_function_identity_arguments(p.oid),
                pg_get_userbyid(p.proowner), p.prosecdef, p.proconfig::text,
                p.proacl::text,
                encode(sha256(convert_to(pg_get_functiondef(p.oid), 'UTF8')), 'hex')
           FROM pg_proc AS p
           JOIN pg_namespace AS n ON n.oid = p.pronamespace
          WHERE n.nspname = 'public'
          ORDER BY 1, 2, 3
       ) TO STDOUT"
  )

  while IFS= read -r rls_line; do
    [[ -n "$rls_line" ]] || continue
    printf 'trigger\t%s\n' "$rls_line" >> "$output"
  done < <(
    psql "$dsn" -v ON_ERROR_STOP=1 -qAtc \
      "COPY (
         SELECT c.relname, t.tgname, t.tgenabled, pg_get_triggerdef(t.oid, true)
           FROM pg_trigger AS t
           JOIN pg_class AS c ON c.oid = t.tgrelid
           JOIN pg_namespace AS n ON n.oid = c.relnamespace
          WHERE n.nspname = 'public' AND NOT t.tgisinternal
          ORDER BY 1, 2
       ) TO STDOUT"
  )

  while IFS= read -r rls_line; do
    [[ -n "$rls_line" ]] || continue
    printf 'default\t%s\n' "$rls_line" >> "$output"
  done < <(
    psql "$dsn" -v ON_ERROR_STOP=1 -qAtc \
      "COPY (
         SELECT c.relname, a.attname, pg_get_expr(d.adbin, d.adrelid)
           FROM pg_attrdef AS d
           JOIN pg_class AS c ON c.oid = d.adrelid
           JOIN pg_namespace AS n ON n.oid = c.relnamespace
           JOIN pg_attribute AS a ON a.attrelid = c.oid AND a.attnum = d.adnum
          WHERE n.nspname = 'public'
          ORDER BY 1, 2
       ) TO STDOUT"
  )
}

runtime_role_probe() {
  local dsn="$1"
  local label="$2"
  local no_context forged_auth

  no_context="$(psql "$dsn" -v ON_ERROR_STOP=1 -tAc "SELECT count(*) FROM users" | tr -d '[:space:]')"
  forged_auth="$(
    psql "$dsn" -v ON_ERROR_STOP=1 -tAc \
      "SELECT set_config('app.auth_context','on',true); SELECT count(*) FROM users" \
      | tail -n1 | tr -d '[:space:]'
  )"
  if [[ "$no_context" != "0" || "$forged_auth" != "0" ]]; then
    printf 'DR DRILL FAILED: %s runtime role bypassed owner isolation (%s/%s)\n' \
      "$label" "$no_context" "$forged_auth" >&2
    exit 1
  fi
  if psql "$dsn" -v ON_ERROR_STOP=1 -tAc "SELECT count(*) FROM audit_events" >/dev/null 2>&1; then
    printf 'DR DRILL FAILED: %s runtime role can read append-only audit rows\n' "$label" >&2
    exit 1
  fi
}

echo "== DR DRILL =="
echo "source db      : ${SOURCE_DB}"
echo "isolated target: ${TARGET_DB} (owner ${TARGET_OWNER})"
echo "workspace      : ${WORK}"

# 1. Seed an isolated source object store (sharded layout, known content).
SRC_OBJ="$WORK/src-objects"
mkdir -p "$SRC_OBJ/ab" "$SRC_OBJ/cd/ef"
printf 'deliverable-one-%s' "$(date -u +%s)" > "$SRC_OBJ/ab/$(openssl rand -hex 8 2>/dev/null || echo abcd1111)"
head -c 4096 /dev/urandom > "$SRC_OBJ/cd/ef/$(openssl rand -hex 8 2>/dev/null || echo cdef2222)"
SRC_OBJ_COUNT="$(find "$SRC_OBJ" -type f | wc -l | tr -d ' ')"

# 2. Back up source db + seeded object store.
BACKUP="$WORK/backup"
SRC_BEFORE="$WORK/source-before.fingerprint"
SRC_AFTER="$WORK/source-after.fingerprint"
database_fingerprint "$SUP_DSN/$SOURCE_DB" "$SRC_BEFORE"
BACKUP_STARTED_MS="$(now_ms)"
NUR_DR_DATABASE_URL="$SUP_DSN/$SOURCE_DB" \
NUR_DR_OBJECT_ROOT="$SRC_OBJ" \
  bash "$ROOT/infra/scripts/dr-backup.sh" "$BACKUP" >/dev/null
BACKUP_FINISHED_MS="$(now_ms)"
database_fingerprint "$SUP_DSN/$SOURCE_DB" "$SRC_AFTER"
if ! cmp -s "$SRC_BEFORE" "$SRC_AFTER"; then
  echo "DR DRILL FAILED: source database changed during the backup window" >&2
  diff -u "$SRC_BEFORE" "$SRC_AFTER" >&2 || true
  exit 1
fi
echo "backup written : $BACKUP"

# 3. Provision a fresh isolated target database.
psql "$SUP_DSN/postgres" -v ON_ERROR_STOP=1 -q \
  -c "DROP DATABASE IF EXISTS ${TARGET_DB} WITH (FORCE)" \
  -c "CREATE DATABASE ${TARGET_DB} OWNER ${TARGET_OWNER}"

# 4. Restore + verify (dr-restore.sh fails closed on any discrepancy).
TGT_OBJ="$WORK/tgt-objects"
RESTORE_STARTED_MS="$(now_ms)"
NUR_DR_RESTORE_DATABASE_URL="$SUP_DSN/$TARGET_DB" \
NUR_DR_RESTORE_OBJECT_ROOT="$TGT_OBJ" \
NUR_DR_RESTORE_CONFIRM_DATABASE="$TARGET_DB" \
NUR_DR_RESTORE_CONFIRM_OBJECT_ROOT="$TGT_OBJ" \
  bash "$ROOT/infra/scripts/dr-restore.sh" "$BACKUP"
RESTORE_FINISHED_MS="$(now_ms)"

# 5. Full data-state parity: schema restoring is not enough. Compare hashes,
# counts, sequences, and the RLS/policy surface without printing private rows.
TARGET_FINGERPRINT="$WORK/target.fingerprint"
database_fingerprint "$SUP_DSN/$TARGET_DB" "$TARGET_FINGERPRINT"
runtime_role_probe "$RUNTIME_BASE_DSN/$SOURCE_DB" source
runtime_role_probe "$RUNTIME_BASE_DSN/$TARGET_DB" target

echo "-- parity --"
echo "tables   : $(grep -c '^table' "$TARGET_FINGERPRINT") fully hashed"
echo "sequences: $(grep -c '^sequence' "$TARGET_FINGERPRINT") state-checked"
echo "objects  : ${SRC_OBJ_COUNT} digest-checked"
echo "backup ms: $((BACKUP_FINISHED_MS - BACKUP_STARTED_MS))"
echo "restore ms: $((RESTORE_FINISHED_MS - RESTORE_STARTED_MS))"

if ! cmp -s "$SRC_BEFORE" "$TARGET_FINGERPRINT"; then
  echo "DR DRILL FAILED: source/target database fingerprint mismatch" >&2
  diff -u "$SRC_BEFORE" "$TARGET_FINGERPRINT" >&2 || true
  exit 1
fi

echo "DR DRILL PASS: isolated restore verified (data, objects, owners, ACLs, functions, triggers, RLS, runtime role)."
