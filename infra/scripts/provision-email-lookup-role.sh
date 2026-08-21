#!/usr/bin/env bash
# Provision the role that owns fn_active_user_id_by_email.
#
# The lookup resolves one account id from one exact email, and every
# invite-by-email path depends on it. It cannot work while the app role owns it,
# because `users` carries FORCE ROW LEVEL SECURITY and FORCE applies to the
# table owner too — the function only ever sees the caller's own row.
#
# `nur_email_lookup` is NOLOGIN and owns the two exact-email lookup functions
# and nothing else. FORCE stays on every table. Run once per database, as a
# superuser, before migrations. The migration grants its column-limited table
# access and function ownership.
#
#   PGSUPERUSER=postgres ./infra/scripts/provision-email-lookup-role.sh nur
set -euo pipefail

DB="${1:-${PGDATABASE:-nur}}"
SUPERUSER="${PGSUPERUSER:-postgres}"
ADMIN_ROLE="${NUR_ADMIN_ROLE:-nur_admin}"
APP_ROLE="${NUR_APP_ROLE:-nur_app}"
CONTAINER="${NUR_POSTGRES_CONTAINER_NAME:-nur_postgres}"
PG_HOST="${NUR_POSTGRES_HOST:-${PGHOST:-127.0.0.1}}"
PG_PORT="${NUR_POSTGRES_PORT:-${PGPORT:-5432}}"
SUPERUSER_PASSWORD="${PGSUPERUSER_PASSWORD:-${PGPASSWORD:-postgres}}"

for identifier in "$SUPERUSER" "$ADMIN_ROLE" "$APP_ROLE"; do
  if [[ ! "$identifier" =~ ^[a-zA-Z_][a-zA-Z0-9_]*$ ]]; then
    printf 'invalid PostgreSQL role identifier: %s\n' "$identifier" >&2
    exit 2
  fi
done

read -r -d '' sql <<SQL || true
DO \$\$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nur_email_lookup') THEN
    CREATE ROLE nur_email_lookup NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
      NOINHERIT NOREPLICATION BYPASSRLS;
  ELSE
    ALTER ROLE nur_email_lookup NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
      NOINHERIT NOREPLICATION BYPASSRLS;
  END IF;
END
\$\$;
GRANT nur_email_lookup TO ${ADMIN_ROLE} WITH ADMIN OPTION;
DO \$\$
BEGIN
  IF pg_has_role('${APP_ROLE}', 'nur_email_lookup', 'MEMBER') THEN
    EXECUTE 'REVOKE nur_email_lookup FROM ${APP_ROLE}';
  END IF;
END
\$\$;
DO \$\$
DECLARE r pg_roles%ROWTYPE;
BEGIN
  SELECT * INTO STRICT r FROM pg_roles WHERE rolname = 'nur_email_lookup';
  IF r.rolcanlogin OR r.rolsuper OR r.rolcreatedb OR r.rolcreaterole
     OR r.rolreplication OR NOT r.rolbypassrls THEN
    RAISE EXCEPTION 'nur_email_lookup role hardening did not persist';
  END IF;
END
\$\$;
SELECT rolname, rolbypassrls, rolcanlogin, rolsuper, rolcreatedb,
       rolcreaterole, rolreplication
  FROM pg_roles WHERE rolname = 'nur_email_lookup';
SQL

if command -v docker >/dev/null && docker ps --format '{{.Names}}' | grep -qx "$CONTAINER"; then
  printf 'provisioning nur_email_lookup in %s (container %s)\n' "$DB" "$CONTAINER" >&2
  printf '%s\n' "$sql" | docker exec -i "$CONTAINER" psql -v ON_ERROR_STOP=1 -U "$SUPERUSER" -d "$DB"
else
  printf 'provisioning nur_email_lookup in %s (local psql %s:%s)\n' "$DB" "$PG_HOST" "$PG_PORT" >&2
  printf '%s\n' "$sql" | PGPASSWORD="$SUPERUSER_PASSWORD" psql \
    -v ON_ERROR_STOP=1 -h "$PG_HOST" -p "$PG_PORT" -U "$SUPERUSER" -d "$DB"
fi
