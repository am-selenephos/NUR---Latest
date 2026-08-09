#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RUNTIME="$ROOT/.nur-runtime"
cd "$ROOT"
if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

printf 'Docker services:\n'
for container in "${NUR_POSTGRES_CONTAINER_NAME:-nur_postgres}" "${NUR_REDIS_CONTAINER_NAME:-nur_redis}"; do
  docker ps -a --filter "name=^/${container}$" --format '{{.Names}} {{.Status}} {{.Ports}}' || true
done

printf '\nLocal data services:\n'
PG_HOST="${NUR_POSTGRES_HOST:-127.0.0.1}"
PG_PORT="${NUR_POSTGRES_PORT:-5432}"
REDIS_HOST="${NUR_REDIS_HOST:-127.0.0.1}"
REDIS_PORT="${NUR_REDIS_PORT:-6379}"
if PGPASSWORD=postgres pg_isready -h "$PG_HOST" -p "$PG_PORT" -U postgres -d postgres >/dev/null 2>&1; then
  printf 'RUNNING postgres %s:%s\n' "$PG_HOST" "$PG_PORT"
else
  printf 'STOPPED postgres %s:%s\n' "$PG_HOST" "$PG_PORT"
fi
if timeout 5s bash -c "</dev/tcp/${REDIS_HOST}/${REDIS_PORT}" >/dev/null 2>&1; then
  printf 'RUNNING redis-compatible %s:%s\n' "$REDIS_HOST" "$REDIS_PORT"
else
  printf 'STOPPED redis-compatible %s:%s\n' "$REDIS_HOST" "$REDIS_PORT"
fi

printf '\nLocal processes:\n'
for name in api worker beat web; do
  pidfile="$RUNTIME/$name.pid"
  if [[ -f "$pidfile" ]] && kill -0 "$(cat "$pidfile")" >/dev/null 2>&1; then
    printf 'RUNNING %s pid %s\n' "$name" "$(cat "$pidfile")"
  else
    printf 'STOPPED %s\n' "$name"
  fi
done

printf '\nHealth:\n'
health_json="$(curl -fsS http://localhost:8000/healthz 2>/dev/null || true)"
ai_provider_mode="${NUR_AI_PROVIDER:-disabled}"
if [[ -n "$health_json" ]]; then
  printf '%s\n' "$health_json"
  ai_provider_mode="$(
    printf '%s' "$health_json" \
      | python3 -c 'import json, sys; print(json.load(sys.stdin).get("ai_provider", "unknown"))' \
      2>/dev/null \
      || printf '%s' "$ai_provider_mode"
  )"
else
  printf 'api healthz unavailable\n'
fi
curl -fsS http://localhost:8000/readyz && printf '\n' || printf 'api readyz unavailable\n'
curl -fsS http://localhost:5173 >/dev/null && printf 'web reachable http://localhost:5173\n' || printf 'web unavailable\n'
printf 'ai provider mode: %s\n' "$ai_provider_mode"
printf 'omega enabled: %s\n' "${NUR_OMEGA_ENABLED:-true}"
printf 'omega scheduler: %s\n' "${NUR_OMEGA_SCHEDULED_CONSOLIDATION:-true}"
