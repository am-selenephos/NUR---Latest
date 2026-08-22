#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RUNTIME="$ROOT/.nur-runtime"
cd "$ROOT"

DEPENDENCIES_ONLY=0
usage() {
  cat >&2 <<'TXT'
Usage: bash infra/scripts/bootstrap-dev.sh [--dependencies-only]

  --dependencies-only  Install only the lockfile-pinned Node and Python
                       dependencies. No environment file, database, Redis,
                       container, role, or migration is touched.
TXT
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dependencies-only)
      DEPENDENCIES_ONLY=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      printf 'Unknown bootstrap option: %s\n' "$1" >&2
      usage
      exit 2
      ;;
  esac
done

API_ROOT="$ROOT/apps/api"
API_VENV="$API_ROOT/.venv"
API_PY="$API_VENV/bin/python"

verify_dependency_locks() {
  [[ -s "$ROOT/package-lock.json" ]] || {
    printf 'Missing package-lock.json; refusing an unlocked Node install.\n' >&2
    return 1
  }
  python3 - "$API_ROOT/requirements.lock" "$API_ROOT/requirements-dev.lock" <<'PY'
from __future__ import annotations

import re
import sys
from pathlib import Path

pin = re.compile(r"[A-Za-z0-9_.-]+==[^;\s]+(?:\s*;\s*.+)?$")
for raw_path in sys.argv[1:]:
    path = Path(raw_path)
    if not path.is_file():
        raise SystemExit(f"Missing Python dependency lock: {path}")
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("-r "):
            included = (path.parent / line[3:].strip()).resolve()
            if not included.is_file():
                raise SystemExit(f"Missing included lock at {path}:{number}: {included}")
            continue
        if not pin.fullmatch(line):
            raise SystemExit(f"Unpinned Python requirement at {path}:{number}: {line}")
PY
}

# A venv survives boots but breaks when the system interpreter moves (common on
# Arch after a Python upgrade). Only an executable interpreter that imports pip
# is reusable; anything else is rebuilt from scratch.
api_venv_healthy() {
  [[ -x "$API_PY" ]] && "$API_PY" -c 'import pip' >/dev/null 2>&1
}

create_api_venv() {
  if command -v uv >/dev/null 2>&1; then
    uv venv --seed "$API_VENV" && return 0
  fi
  if command -v virtualenv >/dev/null 2>&1; then
    virtualenv "$API_VENV" && return 0
  fi
  python3 -m venv "$API_VENV" && return 0
  return 1
}

install_locked_dependencies() {
  verify_dependency_locks
  if ! api_venv_healthy; then
    if [[ -e "$API_VENV" ]]; then
      printf 'Existing %s is not usable; recreating it.\n' "$API_VENV"
      rm -rf "$API_VENV"
    fi
    if ! create_api_venv; then
      cat >&2 <<'TXT'
ERROR: could not create apps/api/.venv with any available mechanism.
Tried, in order:
  1. uv venv --seed   (install: https://docs.astral.sh/uv/ or pacman -S uv)
  2. virtualenv       (install: python3 -m pip install --user virtualenv)
  3. python3 -m venv  (needs working ensurepip; on Arch: pacman -S python-pip)
Install one of the above, then rerun: bash RUN_NUR.sh
TXT
      return 1
    fi
  fi

  # requirements-dev.lock includes requirements.lock. --no-deps makes the two
  # reviewed lockfiles the complete dependency authority instead of allowing
  # pip to discover newer transitives. NUR runs the API from apps/api, so an
  # editable package install (and its otherwise-unlocked build backend) is not
  # needed.
  "$API_PY" -m pip install --disable-pip-version-check --no-deps \
    -r "$API_ROOT/requirements-dev.lock"
  (cd "$ROOT" && npm ci)
}

if [[ "$DEPENDENCIES_ONLY" == "1" ]]; then
  install_locked_dependencies
  printf 'Locked dependency bootstrap complete.\n'
  exit 0
fi

if [[ ! -f .env ]]; then
  cp .env.example .env
  printf 'Created .env from .env.example\n'
fi

set -a
# shellcheck disable=SC1091
source .env
set +a

PG_HOST="${NUR_POSTGRES_HOST:-127.0.0.1}"
PG_PORT="${NUR_POSTGRES_PORT:-5432}"
REDIS_HOST="${NUR_REDIS_HOST:-127.0.0.1}"
REDIS_PORT="${NUR_REDIS_PORT:-6379}"
PG_CONTAINER="${NUR_POSTGRES_CONTAINER_NAME:-nur_postgres}"
REDIS_CONTAINER="${NUR_REDIS_CONTAINER_NAME:-nur_redis}"
SERVICE_MODE="${NUR_SERVICE_MODE:-local}"
PGDATA="$RUNTIME/postgres-data"

container_healthy() {
  local name="$1"
  timeout 5s docker ps --filter "name=^/${name}$" --format '{{.Status}}' | grep -q 'healthy'
}

container_exists() {
  local name="$1"
  timeout 5s docker ps -a --filter "name=^/${name}$" --format '{{.Names}}' | grep -qx "$name"
}

tcp_ready() {
  local host="$1"
  local port="$2"
  timeout 5s bash -c "</dev/tcp/${host}/${port}" >/dev/null 2>&1
}

local_runtime_available() {
  command -v initdb >/dev/null 2>&1 \
    && command -v pg_ctl >/dev/null 2>&1 \
    && command -v postgres >/dev/null 2>&1 \
    && command -v psql >/dev/null 2>&1 \
    && { command -v valkey-server >/dev/null 2>&1 || command -v redis-server >/dev/null 2>&1; }
}

start_local_postgres() {
  mkdir -p "$RUNTIME"
  if PGPASSWORD=postgres pg_isready -h "$PG_HOST" -p "$PG_PORT" -U postgres -d postgres >/dev/null 2>&1; then
    printf 'Reusing local Postgres on %s:%s.\n' "$PG_HOST" "$PG_PORT"
    return 0
  fi
  if [[ ! -s "$PGDATA/PG_VERSION" ]]; then
    rm -rf "$PGDATA"
    initdb -D "$PGDATA" -U postgres --auth=trust >/dev/null
    {
      printf '\n# NUR local runtime\n'
      printf "listen_addresses = '127.0.0.1'\n"
      printf 'port = %s\n' "$PG_PORT"
      printf "unix_socket_directories = '%s'\n" "$RUNTIME"
    } >> "$PGDATA/postgresql.conf"
    {
      printf '\n# NUR local runtime\n'
      printf 'host all all 127.0.0.1/32 trust\n'
      printf 'host all all ::1/128 trust\n'
    } >> "$PGDATA/pg_hba.conf"
  fi
  # The socket directory is already written to postgresql.conf. Keeping it out
  # of pg_ctl's option string avoids re-tokenizing a repository path containing
  # spaces.
  pg_ctl -D "$PGDATA" -l "$RUNTIME/postgres.log" -o "-p ${PG_PORT} -h ${PG_HOST}" -w -t 60 start >/dev/null
}

start_local_redis() {
  mkdir -p "$RUNTIME"
  if tcp_ready "$REDIS_HOST" "$REDIS_PORT"; then
    printf 'Reusing Redis-compatible service on %s:%s.\n' "$REDIS_HOST" "$REDIS_PORT"
    return 0
  fi
  local server
  server="$(command -v valkey-server || command -v redis-server || true)"
  [[ -n "$server" ]] || return 1
  "$server" \
    --daemonize yes \
    --bind "$REDIS_HOST" \
    --port "$REDIS_PORT" \
    --dir "$RUNTIME" \
    --pidfile "$RUNTIME/redis.pid" \
    --logfile "$RUNTIME/redis.log" \
    --save "" \
    --appendonly no >/dev/null
}

set_env_value() {
  local key="$1"
  local value="$2"
  if grep -q "^${key}=" .env; then
    sed -i "s#^${key}=.*#${key}=${value}#" .env
  else
    printf '%s=%s\n' "$key" "$value" >> .env
  fi
  export "$key=$value"
}

docker_run_with_name_retry() {
  local kind="$1"
  local output
  for _ in 1 2 3; do
    if [[ "$kind" == "postgres" ]]; then
      if container_exists "$PG_CONTAINER"; then
        timeout 20s docker start "$PG_CONTAINER" >/dev/null || true
        return 0
      fi
      if output="$(timeout 120s docker run -d \
        --name "$PG_CONTAINER" \
        -e POSTGRES_USER=postgres \
        -e POSTGRES_PASSWORD=postgres \
        -e POSTGRES_DB=postgres \
        -p "${PG_PORT}:5432" \
        -v "${PG_CONTAINER}_data:/var/lib/postgresql/data" \
        --health-cmd "pg_isready -U postgres -d postgres" \
        --health-interval 5s \
        --health-timeout 5s \
        --health-retries 20 \
        pgvector/pgvector:pg16 2>&1)"; then
        return 0
      fi
      if grep -qi 'container name .* already in use' <<<"$output"; then
        PG_CONTAINER="${PG_CONTAINER}_$(date +%s)"
        set_env_value "NUR_POSTGRES_CONTAINER_NAME" "$PG_CONTAINER"
        printf 'Postgres container name was reserved by Docker; retrying as %s.\n' "$PG_CONTAINER" >&2
        continue
      fi
      printf '%s\n' "$output" >&2
      return 1
    fi

    if container_exists "$REDIS_CONTAINER"; then
      timeout 20s docker start "$REDIS_CONTAINER" >/dev/null || true
      return 0
    fi
    if output="$(timeout 120s docker run -d \
      --name "$REDIS_CONTAINER" \
      -p "${REDIS_PORT}:6379" \
      --health-cmd "redis-cli ping" \
      --health-interval 5s \
      --health-timeout 5s \
      --health-retries 20 \
      redis:7-alpine \
      redis-server --appendonly no --save "" 2>&1)"; then
      return 0
    fi
    if grep -qi 'container name .* already in use' <<<"$output"; then
      REDIS_CONTAINER="${REDIS_CONTAINER}_$(date +%s)"
      set_env_value "NUR_REDIS_CONTAINER_NAME" "$REDIS_CONTAINER"
      printf 'Redis container name was reserved by Docker; retrying as %s.\n' "$REDIS_CONTAINER" >&2
      continue
    fi
    printf '%s\n' "$output" >&2
    return 1
  done
  printf 'Docker kept reserving %s container names; cannot start dependencies.\n' "$kind" >&2
  return 1
}

if [[ "$SERVICE_MODE" == "local" ]] && local_runtime_available; then
  start_local_postgres
  start_local_redis
elif container_healthy "$PG_CONTAINER" && container_healthy "$REDIS_CONTAINER"; then
  printf 'Reusing healthy local Postgres and Redis containers.\n'
else
  docker_run_with_name_retry postgres
  docker_run_with_name_retry redis
fi

printf 'Waiting for postgres and redis...\n'
ready_pg=0
for _ in $(seq 1 60); do
  if PGPASSWORD=postgres pg_isready -h "$PG_HOST" -p "$PG_PORT" -U postgres -d postgres >/dev/null 2>&1; then
    ready_pg=1
    break
  fi
  sleep 1
done
if [[ "$ready_pg" != "1" ]]; then
  printf 'Postgres did not become ready on %s:%s. See: docker logs %s\n' "$PG_HOST" "$PG_PORT" "$PG_CONTAINER" >&2
  exit 1
fi
ready_redis=0
for _ in $(seq 1 60); do
  if tcp_ready "$REDIS_HOST" "$REDIS_PORT"; then
    ready_redis=1
    break
  fi
  sleep 1
done
if [[ "$ready_redis" != "1" ]]; then
  printf 'Redis did not become reachable on %s:%s. See: docker logs %s\n' "$REDIS_HOST" "$REDIS_PORT" "$REDIS_CONTAINER" >&2
  exit 1
fi

PGPASSWORD=postgres psql -h "$PG_HOST" -p "$PG_PORT" -U postgres -d postgres -v ON_ERROR_STOP=1 <<'SQL'
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='nur_admin') THEN
    CREATE ROLE nur_admin LOGIN CREATEDB NOSUPERUSER NOCREATEROLE;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='nur_app') THEN
    CREATE ROLE nur_app LOGIN NOSUPERUSER NOCREATEROLE NOCREATEDB NOBYPASSRLS;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='nur_email_lookup') THEN
    CREATE ROLE nur_email_lookup NOLOGIN NOSUPERUSER NOCREATEROLE NOCREATEDB BYPASSRLS;
  END IF;
END $$;
ALTER ROLE nur_admin PASSWORD 'nur_admin_pw';
ALTER ROLE nur_app PASSWORD 'nur_app_pw';
-- Every FORCE-RLS agentic table applies its owner-scoping policy to nur_admin
-- too, and Alembic never sets app.current_user_id. Without BYPASSRLS, every
-- migration-time data statement (legacy-consent invalidation, backfills,
-- reconciliation) silently affects zero rows. Only superuser can grant this,
-- which is why it runs here and not inside a migration.
ALTER ROLE nur_admin BYPASSRLS;
-- Exact-email sharing receives one narrow RLS exception. The app can execute
-- the owned functions but can never SET ROLE to their NOLOGIN owner.
ALTER ROLE nur_email_lookup NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION BYPASSRLS;
GRANT nur_email_lookup TO nur_admin WITH ADMIN OPTION;
DO $$
BEGIN
  IF pg_has_role('nur_app', 'nur_email_lookup', 'MEMBER') THEN
    EXECUTE 'REVOKE nur_email_lookup FROM nur_app';
  END IF;
END $$;
SELECT 'CREATE DATABASE nur OWNER nur_admin'
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname='nur')\gexec
SQL

PGPASSWORD=postgres psql -h "$PG_HOST" -p "$PG_PORT" -U postgres -d nur -v ON_ERROR_STOP=1 <<'SQL'
ALTER SCHEMA public OWNER TO nur_admin;
GRANT USAGE ON SCHEMA public TO nur_app;
SQL

install_locked_dependencies

(cd "$API_ROOT" && "$API_PY" -m alembic.config upgrade head)

printf 'Bootstrap complete. Start with: bash infra/scripts/start-nur.sh disabled\n'
