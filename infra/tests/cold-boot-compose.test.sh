#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
COMPOSE="$ROOT/docker-compose.yml"
INIT="$ROOT/infra/postgres/001-nur-roles-and-database.sql"

[[ -f "$INIT" ]]

grep -Fq './infra/postgres/001-nur-roles-and-database.sql:/docker-entrypoint-initdb.d/001-nur-roles-and-database.sql:ro' "$COMPOSE"
grep -Fq 'CREATE ROLE nur_admin' "$INIT"
grep -Fq 'ALTER ROLE nur_admin BYPASSRLS' "$INIT"
grep -Fq 'CREATE ROLE nur_app' "$INIT"
grep -Fq 'CREATE DATABASE nur OWNER nur_admin' "$INIT"
grep -Fq 'ALTER SCHEMA public OWNER TO nur_admin' "$INIT"
grep -Fq 'GRANT USAGE ON SCHEMA public TO nur_app' "$INIT"

grep -Fq 'http://127.0.0.1:8000/readyz' "$COMPOSE"
grep -Fq 'http://127.0.0.1:5173/healthz' "$COMPOSE"

printf 'cold boot compose contract passed.\n'
