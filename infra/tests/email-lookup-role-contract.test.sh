#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
SCRIPT="$ROOT_DIR/infra/scripts/provision-email-lookup-role.sh"

bash -n "$SCRIPT"
grep -q 'NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE' "$SCRIPT"
grep -q 'NOREPLICATION BYPASSRLS' "$SCRIPT"
grep -q 'rolsuper' "$SCRIPT"
grep -q 'rolcreatedb' "$SCRIPT"
grep -q 'rolcreaterole' "$SCRIPT"
grep -q 'rolreplication' "$SCRIPT"
grep -q "REVOKE nur_email_lookup FROM" "$SCRIPT"

echo "email lookup role contract PASS"
