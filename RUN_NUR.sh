#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-disabled}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNTIME="$ROOT/.nur-runtime"
cd "$ROOT"

DATE_STAMP="${NUR_PACKAGE_DATE:-$(date +%Y%m%d)}"
WEB_URL="${WEB_ORIGIN:-http://localhost:5173}"
API_URL="${API_ORIGIN:-http://localhost:8000}"

on_error() {
  local line="${1:-unknown}"
  printf '\nNUR boot stopped at line %s.\n' "$line" >&2
  printf 'Useful next checks:\n' >&2
  printf '  bash RUN_NUR.sh status\n' >&2
  printf '  bash RUN_NUR.sh logs\n' >&2
  printf '  docker compose logs postgres redis\n' >&2
}
trap 'on_error "$LINENO"' ERR

banner() {
  cat <<'TXT'

NUR
Bootable local private-context intelligence beta.
One file starts Postgres, Redis, API, worker, Omega scheduler, web, and demo.

TXT
}

die() {
  printf 'ERROR: %s\n' "$1" >&2
  exit 1
}

require_repo_root() {
  [[ -d apps/api && -d apps/web && -d infra/scripts ]] || die "Run this from the NUR repo root or keep RUN_NUR.sh in the root folder."
}

require_tool() {
  command -v "$1" >/dev/null 2>&1 || die "Missing $1. Install it, then rerun bash RUN_NUR.sh doctor."
}

docker_ready() {
  docker info >/dev/null 2>&1 || die "Docker is not running. Start Docker Desktop/Docker Engine, then rerun bash RUN_NUR.sh."
}

load_env() {
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
  WEB_URL="${WEB_ORIGIN:-http://localhost:5173}"
  API_URL="${API_ORIGIN:-http://localhost:8000}"
}

require_openai_local_secret() {
  if ! bash infra/scripts/validate-openai-local.sh >/dev/null; then
    cat >&2 <<'TXT'
ERROR: OpenAI mode requires a valid mode-600 local .env.local created by:
  bash infra/scripts/configure-openai-local.sh
No API key was read from chat, source, logs, or artifacts.
TXT
    exit 1
  fi
}

set_env_value() {
  local key="$1"
  local value="$2"
  if grep -q "^${key}=" .env; then
    sed -i "s#^${key}=.*#${key}=${value}#" .env
  else
    printf '%s=%s\n' "$key" "$value" >> .env
  fi
}

port_listening() {
  local port="$1"
  ss -ltn "( sport = :$port )" 2>/dev/null | grep -q ":$port"
}

docker_publishes_port() {
  local container="$1"
  local port="$2"
  timeout 5s docker ps --filter "name=^/${container}$" --format '{{.Ports}}' | grep -q "0.0.0.0:${port}->"
}

docker_claims_host_port() {
  local port="$1"
  timeout 5s docker ps --format '{{.Ports}}' \
    | tr ',' '\n' \
    | grep -q "0.0.0.0:${port}->"
}

docker_host_port() {
  local container="$1"
  local container_port="$2"
  timeout 5s docker ps --filter "name=^/${container}$" --format '{{.Ports}}' \
    | tr ',' '\n' \
    | sed -nE "s/.*0\\.0\\.0\\.0:([0-9]+)->${container_port}\\/tcp.*/\\1/p" \
    | head -n 1
}

port_unavailable() {
  local port="$1"
  port_listening "$port" || docker_claims_host_port "$port"
}

local_pid_running() {
  local pidfile="$1"
  [[ -s "$pidfile" ]] && kill -0 "$(cat "$pidfile")" >/dev/null 2>&1
}

local_postgres_runtime_running() {
  local pidfile="$RUNTIME/postgres-data/postmaster.pid"
  [[ -s "$pidfile" ]] || return 1
  local pid
  pid="$(head -n 1 "$pidfile" 2>/dev/null || true)"
  [[ -n "$pid" ]] && kill -0 "$pid" >/dev/null 2>&1
}

local_redis_runtime_running() {
  local_pid_running "$RUNTIME/redis.pid"
}

free_port_from() {
  local port="$1"
  while port_unavailable "$port"; do
    port=$((port + 1))
  done
  printf '%s\n' "$port"
}

repo_suffix() {
  printf '%s' "$ROOT" | sha256sum | awk '{print substr($1, 1, 8)}'
}

ensure_env() {
  if [[ ! -f .env ]]; then
    cp .env.example .env
    chmod 600 .env
    printf 'Created local .env from .env.example\n'
  fi
  load_env

  local suffix="${NUR_DOCKER_SUFFIX:-}"
  if [[ -z "$suffix" || "$suffix" == "local" ]]; then
    suffix="$(repo_suffix)"
    set_env_value "NUR_DOCKER_SUFFIX" "$suffix"
  fi
  local pg_container="${NUR_POSTGRES_CONTAINER_NAME:-}"
  if [[ -z "$pg_container" || "$pg_container" == "nur_postgres" || "$pg_container" == "nur_postgres_local" ]]; then
    pg_container="nur_postgres_${suffix}"
    set_env_value "NUR_POSTGRES_CONTAINER_NAME" "$pg_container"
  fi
  local redis_container="${NUR_REDIS_CONTAINER_NAME:-}"
  if [[ -z "$redis_container" || "$redis_container" == "nur_redis" || "$redis_container" == "nur_redis_local" ]]; then
    redis_container="nur_redis_${suffix}"
    set_env_value "NUR_REDIS_CONTAINER_NAME" "$redis_container"
  fi

  local pg_port="${NUR_POSTGRES_PORT:-5432}"
  local existing_pg_port
  if [[ "${NUR_SERVICE_MODE:-local}" == "local" ]]; then
    existing_pg_port=""
  else
    existing_pg_port="$(docker_host_port "$pg_container" "5432" || true)"
  fi
  if [[ -n "$existing_pg_port" ]] && port_listening "$existing_pg_port"; then
    pg_port="$existing_pg_port"
    set_env_value "NUR_POSTGRES_PORT" "$pg_port"
    set_env_value "DATABASE_URL" "postgresql+asyncpg://nur_app:nur_app_pw@localhost:${pg_port}/nur"
    set_env_value "ALEMBIC_DATABASE_URL" "postgresql+asyncpg://nur_admin:nur_admin_pw@localhost:${pg_port}/nur"
  elif [[ "$pg_port" == "5432" ]] && port_unavailable "$pg_port" && ! docker_publishes_port "$pg_container" "$pg_port" && ! local_postgres_runtime_running; then
    pg_port="$(free_port_from 15432)"
    printf 'Port 5432 is busy, so NUR will use Postgres host port %s.\n' "$pg_port"
    set_env_value "NUR_POSTGRES_PORT" "$pg_port"
    set_env_value "DATABASE_URL" "postgresql+asyncpg://nur_app:nur_app_pw@localhost:${pg_port}/nur"
    set_env_value "ALEMBIC_DATABASE_URL" "postgresql+asyncpg://nur_admin:nur_admin_pw@localhost:${pg_port}/nur"
  fi

  # Keep the connection strings pinned to whichever port was actually resolved,
  # on every boot rather than only inside the two branches above.
  #
  # Neither branch runs once .env carries a non-5432 NUR_POSTGRES_PORT from an
  # earlier boot: the first needs a published container port, and the second
  # tests `pg_port == 5432`. DATABASE_URL then keeps a stale value indefinitely
  # while role provisioning targets NUR_POSTGRES_PORT — so the API, Alembic and
  # bootstrap can end up on *different* Postgres instances. Observed live: the
  # app on 15432 against a second instance provisioned on 15433, which left the
  # agent_ops_* boundary owned by a role with no BYPASSRLS and therefore silently
  # unable to see across owners.
  set_env_value "NUR_POSTGRES_PORT" "$pg_port"
  set_env_value "DATABASE_URL" "postgresql+asyncpg://nur_app:nur_app_pw@localhost:${pg_port}/nur"
  set_env_value "ALEMBIC_DATABASE_URL" "postgresql+asyncpg://nur_admin:nur_admin_pw@localhost:${pg_port}/nur"

  local redis_port="${NUR_REDIS_PORT:-6379}"
  local existing_redis_port
  if [[ "${NUR_SERVICE_MODE:-local}" == "local" ]]; then
    existing_redis_port=""
  else
    existing_redis_port="$(docker_host_port "$redis_container" "6379" || true)"
  fi
  if [[ -n "$existing_redis_port" ]] && port_listening "$existing_redis_port"; then
    redis_port="$existing_redis_port"
    set_env_value "NUR_REDIS_PORT" "$redis_port"
    set_env_value "REDIS_URL" "redis://localhost:${redis_port}/0"
  elif [[ "$redis_port" == "6379" ]] && port_unavailable "$redis_port" && ! docker_publishes_port "$redis_container" "$redis_port" && ! local_redis_runtime_running; then
    redis_port="$(free_port_from 16379)"
    printf 'Port 6379 is busy, so NUR will use Redis host port %s.\n' "$redis_port"
    set_env_value "NUR_REDIS_PORT" "$redis_port"
    set_env_value "REDIS_URL" "redis://localhost:${redis_port}/0"
  fi

  # Same re-sync for Redis, for the same reason: a stale REDIS_URL would point
  # the API and the worker at different brokers, so published work would be
  # queued where nothing is listening.
  set_env_value "NUR_REDIS_PORT" "$redis_port"
  set_env_value "REDIS_URL" "redis://localhost:${redis_port}/0"

  set_env_value "NUR_ENABLE_OMEGA_RESEARCH" "true"
  set_env_value "VITE_NUR_ENABLE_OMEGA_RESEARCH" "true"
  set_env_value "NUR_OMEGA_ENABLED" "true"
  set_env_value "NUR_OMEGA_SCHEDULED_CONSOLIDATION" "true"
  set_env_value "NUR_SERVICE_MODE" "${NUR_SERVICE_MODE:-local}"
  if [[ "${NUR_DEMO_OWNER_EMAIL:-}" == "owner@nur.local" || -z "${NUR_DEMO_OWNER_EMAIL:-}" ]]; then
    set_env_value "NUR_DEMO_OWNER_EMAIL" "owner@nur.app"
  fi
  if [[ "${NUR_DEMO_RECIPIENT_EMAIL:-}" == "recipient@nur.local" || -z "${NUR_DEMO_RECIPIENT_EMAIL:-}" ]]; then
    set_env_value "NUR_DEMO_RECIPIENT_EMAIL" "recipient@nur.app"
  fi
  load_env
}

doctor() {
  require_repo_root
  require_tool docker
  require_tool node
  require_tool npm
  require_tool python3
  docker_ready
  ensure_env
  bash infra/scripts/dev-doctor.sh
}

wait_url() {
  local label="$1"
  local url="$2"
  for _ in $(seq 1 90); do
    if curl -fsS "$url" >/dev/null 2>&1; then
      printf 'PASS %s reachable: %s\n' "$label" "$url"
      return 0
    fi
    sleep 1
  done
  printf 'FAIL %s did not become reachable: %s\n' "$label" "$url" >&2
  bash RUN_NUR.sh logs || true
  return 1
}

process_up() {
  local name="$1"
  local pidfile=".nur-runtime/${name}.pid"
  [[ -f "$pidfile" ]] && kill -0 "$(cat "$pidfile")" >/dev/null 2>&1
}

health_gates() {
  wait_url "api healthz" "${API_URL}/healthz"
  wait_url "api readyz" "${API_URL}/readyz"
  wait_url "web" "${WEB_URL}"
  process_up api || die "API process is not running. See bash RUN_NUR.sh logs."
  process_up worker || die "Worker process is not running. See bash RUN_NUR.sh logs."
  process_up beat || die "Omega scheduler/beat process is not running. See bash RUN_NUR.sh logs."
  process_up web || die "Web process is not running. See bash RUN_NUR.sh logs."
}

openai_health_gate() {
  apps/api/.venv/bin/python - <<'PY'
import os
import sys
import httpx

api = os.environ.get("API_ORIGIN", "http://localhost:8000")
health = httpx.get(f"{api}/healthz", timeout=10).json()
if health.get("ai_provider") != "openai":
    print("ERROR: /healthz did not report ai_provider=openai.", file=sys.stderr)
    raise SystemExit(1)
ready = httpx.get(f"{api}/readyz", timeout=10).json()
if ready.get("status") != "ready":
    print("ERROR: /readyz is not ready.", file=sys.stderr)
    raise SystemExit(1)
metrics = httpx.get(f"{api}/metrics", timeout=10).text
if 'nur_ai_provider_configured{provider="openai"} 1' not in metrics:
    print("ERROR: /metrics did not expose openai provider label.", file=sys.stderr)
    raise SystemExit(1)
# Truthful boundary: healthz/readyz/metrics reporting provider=openai proves the
# server MODE is selected and the process is healthy. It does NOT prove the
# credential is valid or that the model is reachable — only a real provider
# response does that. Run the live provider smoke to prove authentication.
print("PASS OpenAI configuration/mode gates: provider=openai selected; healthz, readyz, metrics healthy.")
print("NOT PROVEN here: live authentication and model access. Run the live provider smoke to test the credential.")
PY
}

start_all() {
  local ai_mode="$1"
  banner
  if [[ "$ai_mode" == "openai" ]]; then
    require_openai_local_secret
  fi
  doctor
  if [[ "$ai_mode" == "openai" ]]; then
    set_env_value "NUR_AI_PROVIDER" "openai"
  else
    set_env_value "NUR_AI_PROVIDER" "disabled"
  fi
  load_env
  printf 'Stopping stale local processes before fresh %s boot...\n' "$ai_mode"
  bash infra/scripts/stop-nur.sh || true
  printf 'Bootstrapping local dependencies and database...\n'
  bash infra/scripts/bootstrap-dev.sh
  printf 'Starting complete NUR system (%s mode)...\n' "$ai_mode"
  bash infra/scripts/start-nur.sh "$ai_mode"
  health_gates
  if [[ "$ai_mode" == "openai" ]]; then
    openai_health_gate
  fi
  printf 'Seeding demo data...\n'
  bash infra/scripts/seed-demo-nur.sh
  printf '\nNUR is ready.\n'
  print_urls
  bash infra/scripts/open-nur.sh || true
  printf '\nLogs: bash RUN_NUR.sh logs\n'
}

print_urls() {
  cat <<TXT
Owner app: ${WEB_URL}
Owner Talk: ${WEB_URL}/talk
Owner Systems: ${WEB_URL}/systems
Omega: ${WEB_URL}/universe/omega
Omega Review: ${WEB_URL}/universe/omega/review
API health: ${API_URL}/healthz

Demo credentials:
Owner: ${NUR_DEMO_OWNER_EMAIL:-owner@nur.app} / ${NUR_DEMO_OWNER_PASSWORD:-owner-demo-pass-123}
Recipient: ${NUR_DEMO_RECIPIENT_EMAIL:-recipient@nur.app} / ${NUR_DEMO_RECIPIENT_PASSWORD:-recipient-demo-pass-123}
TXT
}

require_development() {
  ensure_env
  [[ "${APP_ENV:-development}" != "production" ]] || die "reset-demo is refused when APP_ENV=production."
}

case "$MODE" in
  disabled|"")
    start_all disabled
    ;;
  openai)
    start_all openai
    curl -fsS "${API_URL}/metrics" >/dev/null && printf 'PASS metrics reachable with provider mode configured.\n'
    bash infra/scripts/openai-smoke-local.sh
    ;;
  seed)
    ensure_env
    bash infra/scripts/seed-demo-nur.sh
    ;;
  status)
    ensure_env
    bash infra/scripts/status-nur.sh
    ;;
  stop)
    bash infra/scripts/stop-nur.sh
    ;;
  logs)
    bash infra/scripts/logs-nur.sh
    ;;
  doctor)
    doctor
    ;;
  reset-demo)
    require_development
    bash infra/scripts/stop-nur.sh || true
    for container in "${NUR_POSTGRES_CONTAINER_NAME:-}" "${NUR_REDIS_CONTAINER_NAME:-}"; do
      [[ -n "$container" ]] && timeout 20s docker rm -f "$container" >/dev/null 2>&1 || true
    done
    [[ -n "${NUR_POSTGRES_CONTAINER_NAME:-}" ]] && timeout 20s docker volume rm "${NUR_POSTGRES_CONTAINER_NAME}_data" >/dev/null 2>&1 || true
    rm -rf .nur-runtime
    start_all disabled
    ;;
  package)
    ensure_env
    bash infra/scripts/package-bootable.sh "/home/nur/Downloads/NUR_FULL_SYSTEM_COMPLETE_V197_AI_${DATE_STAMP}.zip"
    ;;
  *)
    cat <<TXT
Unknown mode: $MODE
Use:
  bash RUN_NUR.sh
  bash RUN_NUR.sh disabled
  bash RUN_NUR.sh openai
  bash RUN_NUR.sh seed
  bash RUN_NUR.sh status
  bash RUN_NUR.sh stop
  bash RUN_NUR.sh logs
  bash RUN_NUR.sh doctor
  bash RUN_NUR.sh reset-demo
  bash RUN_NUR.sh package
TXT
    exit 2
    ;;
esac
