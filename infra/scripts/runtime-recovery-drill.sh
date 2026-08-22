#!/usr/bin/env bash
# Controlled local crash/recovery proof for the four stateful runtime edges:
# API, Celery worker, Celery Beat, and Redis. The script refuses production,
# unknown processes, and Redis instances not owned by NUR's local bootstrap.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RUNTIME="$ROOT/.nur-runtime"
CONFIRM="${NUR_RECOVERY_DRILL_CONFIRM:-}"

if [[ "$CONFIRM" != "local-only" ]]; then
  printf 'Set NUR_RECOVERY_DRILL_CONFIRM=local-only to run the destructive local drill.\n' >&2
  exit 2
fi
if [[ ! -f "$ROOT/.env" ]]; then
  printf 'Missing .env; local runtime ownership cannot be established.\n' >&2
  exit 2
fi

set -a
# shellcheck disable=SC1091
source "$ROOT/.env"
set +a
if [[ "${APP_ENV:-development}" == "production" ]]; then
  printf 'Refusing to run a crash drill with APP_ENV=production.\n' >&2
  exit 2
fi

API_URL="${NUR_RECOVERY_API_URL:-http://127.0.0.1:8000}"
REDIS_HOST="${NUR_REDIS_HOST:-127.0.0.1}"
REDIS_PORT="${NUR_REDIS_PORT:-6379}"
REDIS_CONTAINER="${NUR_REDIS_CONTAINER_NAME:-}"
TIMEOUT_SECONDS="${NUR_RECOVERY_TIMEOUT_SECONDS:-60}"
START_SCRIPT="$ROOT/infra/scripts/start-nur.sh"

recover_on_failure() {
  local status=$?
  trap - EXIT
  if [[ $status -ne 0 ]]; then
    printf 'Recovery drill failed; restoring the disabled-provider local stack.\n' >&2
    bash "$START_SCRIPT" disabled >/dev/null 2>&1 || true
  fi
  exit "$status"
}
trap recover_on_failure EXIT

deadline() {
  printf '%s' "$((SECONDS + TIMEOUT_SECONDS))"
}

wait_until_dead() {
  local pid="$1"
  local end
  end="$(deadline)"
  while kill -0 "$pid" >/dev/null 2>&1; do
    if (( SECONDS >= end )); then
      printf 'Timed out waiting for pid %s to stop.\n' "$pid" >&2
      return 1
    fi
    sleep 0.1
  done
}

managed_pid() {
  local name="$1"
  local expected="$2"
  local pidfile="$RUNTIME/$name.pid"
  local pid command

  [[ -s "$pidfile" ]] || { printf 'Missing managed pidfile: %s\n' "$pidfile" >&2; return 1; }
  pid="$(cat "$pidfile")"
  [[ "$pid" =~ ^[0-9]+$ ]] || { printf 'Invalid pid in %s\n' "$pidfile" >&2; return 1; }
  kill -0 "$pid" >/dev/null 2>&1 || { printf '%s pid %s is not alive.\n' "$name" "$pid" >&2; return 1; }
  command="$(tr '\0' ' ' < "/proc/$pid/cmdline")"
  [[ "$command" == *"$expected"* ]] || {
    printf 'Refusing unknown %s pid %s: %s\n' "$name" "$pid" "$command" >&2
    return 1
  }
  printf '%s' "$pid"
}

wait_api_ready() {
  local end
  end="$(deadline)"
  until curl -fsS "$API_URL/readyz" >/dev/null 2>&1; do
    if (( SECONDS >= end )); then
      printf 'API did not become ready at %s.\n' "$API_URL" >&2
      return 1
    fi
    sleep 0.2
  done
}

wait_api_unready() {
  local end
  end="$(deadline)"
  while curl -fsS "$API_URL/readyz" >/dev/null 2>&1; do
    if (( SECONDS >= end )); then
      printf 'API remained ready after its required dependency was stopped.\n' >&2
      return 1
    fi
    sleep 0.1
  done
}

wait_redis() {
  local expected="$1"
  local end state
  end="$(deadline)"
  while true; do
    if timeout 2s bash -c "</dev/tcp/${REDIS_HOST}/${REDIS_PORT}" >/dev/null 2>&1; then
      state="up"
    else
      state="down"
    fi
    [[ "$state" == "$expected" ]] && return 0
    if (( SECONDS >= end )); then
      printf 'Redis did not become %s at %s:%s.\n' "$expected" "$REDIS_HOST" "$REDIS_PORT" >&2
      return 1
    fi
    sleep 0.1
  done
}

wait_worker_ready() {
  local end output
  end="$(deadline)"
  while true; do
    output="$(
      cd "$ROOT/apps/api"
      timeout 8s .venv/bin/celery -A app.workers.celery_app.celery inspect ping --timeout=3 2>/dev/null || true
    )"
    [[ "$output" == *"pong"* ]] && return 0
    if (( SECONDS >= end )); then
      printf 'Celery worker did not answer ping.\n' >&2
      return 1
    fi
    sleep 0.2
  done
}

wait_beat_ready() {
  local pid="$1"
  local end
  end="$(deadline)"
  while true; do
    if kill -0 "$pid" >/dev/null 2>&1 \
      && grep -Eq 'celery beat|beat: Starting' "$RUNTIME/beat.log" 2>/dev/null; then
      return 0
    fi
    if (( SECONDS >= end )); then
      printf 'Celery Beat did not reach its startup marker.\n' >&2
      return 1
    fi
    sleep 0.1
  done
}

crash_managed() {
  local name="$1"
  local expected="$2"
  local pid
  pid="$(managed_pid "$name" "$expected")"
  kill -KILL -- "-$pid" >/dev/null 2>&1 || kill -KILL "$pid"
  rm -f "$RUNTIME/$name.pid"
  wait_until_dead "$pid"
  printf '%s' "$pid"
}

restart_stack() {
  bash "$START_SCRIPT" disabled >/dev/null
}

printf '== NUR CONTROLLED RUNTIME RECOVERY DRILL ==\n'
restart_stack
wait_api_ready
wait_worker_ready

old_api="$(crash_managed api 'uvicorn app.main:app')"
wait_api_unready
restart_stack
wait_api_ready
new_api="$(managed_pid api 'uvicorn app.main:app')"
[[ "$new_api" != "$old_api" ]] || { printf 'API pid did not change.\n' >&2; exit 1; }
printf 'PASS api crash/restart: %s -> %s\n' "$old_api" "$new_api"

old_worker="$(crash_managed worker 'celery -A app.workers.celery_app.celery worker')"
restart_stack
wait_worker_ready
new_worker="$(managed_pid worker 'celery -A app.workers.celery_app.celery worker')"
[[ "$new_worker" != "$old_worker" ]] || { printf 'Worker pid did not change.\n' >&2; exit 1; }
printf 'PASS worker crash/restart: %s -> %s\n' "$old_worker" "$new_worker"

old_beat="$(crash_managed beat 'celery -A app.workers.celery_app.celery beat')"
restart_stack
new_beat="$(managed_pid beat 'celery -A app.workers.celery_app.celery beat')"
wait_beat_ready "$new_beat"
[[ "$new_beat" != "$old_beat" ]] || { printf 'Beat pid did not change.\n' >&2; exit 1; }
printf 'PASS beat crash/restart: %s -> %s\n' "$old_beat" "$new_beat"

redis_pidfile="$RUNTIME/redis.pid"
if [[ -s "$redis_pidfile" ]] && kill -0 "$(cat "$redis_pidfile")" >/dev/null 2>&1; then
  redis_pid="$(cat "$redis_pidfile")"
  redis_command="$(tr '\0' ' ' < "/proc/$redis_pid/cmdline")"
  if [[ "$redis_command" != *redis-server* && "$redis_command" != *valkey-server* ]]; then
    printf 'Refusing unknown Redis pid %s: %s\n' "$redis_pid" "$redis_command" >&2
    exit 1
  fi
  [[ "$redis_command" == *":$REDIS_PORT"* ]] || {
    printf 'Refusing Redis-compatible pid %s on an unexpected port: %s\n' \
      "$redis_pid" "$redis_command" >&2
    exit 1
  }
  kill -KILL "$redis_pid"
  rm -f "$redis_pidfile"
elif [[ -n "$REDIS_CONTAINER" ]] \
  && docker inspect "$REDIS_CONTAINER" >/dev/null 2>&1 \
  && [[ "$(docker inspect -f '{{.State.Running}}' "$REDIS_CONTAINER")" == "true" ]]; then
  docker stop --time 0 "$REDIS_CONTAINER" >/dev/null
else
  printf 'Refusing to crash Redis: no NUR-managed local process/container was found.\n' >&2
  exit 2
fi

wait_redis down
wait_api_unready
restart_stack
wait_redis up
wait_api_ready
wait_worker_ready
beat_pid="$(managed_pid beat 'celery -A app.workers.celery_app.celery beat')"
wait_beat_ready "$beat_pid"
printf 'PASS redis crash/recovery: API, worker, and Beat recovered\n'
printf 'RUNTIME RECOVERY DRILL PASS\n'
