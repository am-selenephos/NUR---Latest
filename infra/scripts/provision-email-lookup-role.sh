#!/usr/bin/env bash
# Provision the role that owns fn_active_user_id_by_email.
#
# The lookup resolves one account id from one exact email, and every
# invite-by-email path depends on it. It cannot work while the app role owns it,
# because `users` carries FORCE ROW LEVEL SECURITY and FORCE applies to the
# table owner too — the function only ever sees the caller's own row.
#
# `nur_email_lookup` is NOLOGIN and owns that one function and nothing else.
# FORCE stays on every table. Run once per database, as a superuser, before
# migrating to 0034.
#
#   PGSUPERUSER=postgres ./infra/scripts/provision-email-lookup-role.sh nur
set -euo pipefail

DB="${1:-${PGDATABASE:-nur}}"
SUPERUSER="${PGSUPERUSER:-postgres}"
APP_ROLE="${NUR_APP_ROLE:-nur_app}"
CONTAINER="${NUR_POSTGRES_CONTAINER_NAME:-nur_postgres}"

read -r -d '' sql <<SQL || true
DO \$\$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nur_email_lookup') THEN
    CREATE ROLE nur_email_lookup NOLOGIN BYPASSRLS;
  ELSE
    ALTER ROLE nur_email_lookup NOLOGIN BYPASSRLS;
  END IF;
END
\$\$;
GRANT nur_email_lookup TO ${APP_ROLE};
-- A role must be able to create in a schema to own an object there, otherwise
-- ALTER FUNCTION ... OWNER TO fails with "permission denied for schema public".
GRANT USAGE, CREATE ON SCHEMA public TO nur_email_lookup;
-- BYPASSRLS exempts the role from policies, not from table grants. The function
-- reads exactly one column of one table, so that is all this grants.
GRANT SELECT ON users TO nur_email_lookup;
SELECT rolname, rolbypassrls, rolcanlogin FROM pg_roles WHERE rolname = 'nur_email_lookup';
SQL

if command -v docker >/dev/null && docker ps --format '{{.Names}}' | grep -qx "$CONTAINER"; then
  printf 'provisioning nur_email_lookup in %s (container %s)\n' "$DB" "$CONTAINER" >&2
  printf '%s\n' "$sql" | docker exec -i "$CONTAINER" psql -v ON_ERROR_STOP=1 -U "$SUPERUSER" -d "$DB"
else
  printf 'provisioning nur_email_lookup in %s (local psql)\n' "$DB" >&2
  printf '%s\n' "$sql" | psql -v ON_ERROR_STOP=1 -U "$SUPERUSER" -d "$DB"
fi
