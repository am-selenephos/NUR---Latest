#!/usr/bin/env bash
# Clean-install and service-independent cold-process proof for an extracted NUR
# release. Postgres/Redis/worker/Beat readiness is deliberately not inferred.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
INSTALL="${NUR_FRESH_EXTRACT_INSTALL:-0}"
COLD_BOOT="${NUR_FRESH_EXTRACT_COLD_BOOT:-0}"
STATIC_CHECKS="${NUR_FRESH_EXTRACT_STATIC_CHECKS:-1}"
BUILD_CHECKS="${NUR_FRESH_EXTRACT_BUILD_CHECKS:-1}"
RUNTIME="$(mktemp -d)"
PIDS=()

cleanup() {
  local pid
  for pid in "${PIDS[@]}"; do
    kill -TERM "$pid" 2>/dev/null || true
  done
  for pid in "${PIDS[@]}"; do
    wait "$pid" 2>/dev/null || true
  done
  rm -rf "$RUNTIME"
}
trap cleanup EXIT

case "$INSTALL" in 0|1) ;; *) printf 'NUR_FRESH_EXTRACT_INSTALL must be 0 or 1.\n' >&2; exit 2 ;; esac
case "$COLD_BOOT" in 0|1) ;; *) printf 'NUR_FRESH_EXTRACT_COLD_BOOT must be 0 or 1.\n' >&2; exit 2 ;; esac
case "$STATIC_CHECKS" in 0|1) ;; *) printf 'NUR_FRESH_EXTRACT_STATIC_CHECKS must be 0 or 1.\n' >&2; exit 2 ;; esac
case "$BUILD_CHECKS" in 0|1) ;; *) printf 'NUR_FRESH_EXTRACT_BUILD_CHECKS must be 0 or 1.\n' >&2; exit 2 ;; esac
if [[ "$COLD_BOOT" == "1" && "$INSTALL" != "1" ]]; then
  printf 'Cold-process proof requires the clean install mode.\n' >&2
  exit 2
fi

for required in package.json package-lock.json apps/api/requirements.lock apps/api/requirements-dev.lock; do
  [[ -s "$ROOT/$required" ]] || {
    printf 'Fresh-extract contract missing %s\n' "$required" >&2
    exit 1
  }
done

if [[ "$INSTALL" != "1" ]]; then
  printf 'CLEAN_INSTALL=NOT_RUN_REQUESTED\n'
  printf 'STATIC_GATES=NOT_RUN_REQUESTED\n'
  printf 'PRODUCTION_BUILD=NOT_RUN_REQUESTED\n'
  printf 'APPLICATION_COLD_BOOT=NOT_RUN_REQUESTED\n'
  printf 'FULL_STACK_COLD_BOOT=NOT_RUN_REQUIRES_POSTGRES_REDIS\n'
  exit 0
fi

(cd "$ROOT" && bash infra/scripts/bootstrap-dev.sh --dependencies-only)
if [[ "$BUILD_CHECKS" == "1" ]]; then
  (cd "$ROOT" && npm run web:build)
  printf 'PRODUCTION_BUILD=PASS\n'
else
  printf 'PRODUCTION_BUILD=NOT_RUN_SEPARATE_RELEASE_GATE_REQUIRED\n'
fi
PYTHONPATH="$ROOT/apps/api" "$ROOT/apps/api/.venv/bin/python" -c \
  'from app.main import app; spec=app.openapi(); assert spec["paths"]; print("OPENAPI_PATHS=%d" % len(spec["paths"]))'
printf 'CLEAN_INSTALL=PASS\n'

if [[ "$STATIC_CHECKS" == "1" ]]; then
  (cd "$ROOT" && npm run web:typecheck)
  (cd "$ROOT" && npm run web:test)
  (cd "$ROOT" && npm run mobile:typecheck)
  "$ROOT/apps/api/.venv/bin/python" -m ruff check "$ROOT/apps/api"
  printf 'STATIC_GATES=PASS\n'
else
  printf 'STATIC_GATES=NOT_RUN_SEPARATE_RELEASE_GATE_REQUIRED\n'
fi

if [[ "$COLD_BOOT" != "1" ]]; then
  printf 'APPLICATION_COLD_BOOT=NOT_RUN_REQUESTED\n'
  printf 'FULL_STACK_COLD_BOOT=NOT_RUN_REQUIRES_POSTGRES_REDIS\n'
  exit 0
fi

free_port() {
  python3 - <<'PY'
import socket
with socket.socket() as sock:
    sock.bind(("127.0.0.1", 0))
    print(sock.getsockname()[1])
PY
}

wait_http() {
  local label="$1"
  local url="$2"
  local pid="$3"
  for _ in $(seq 1 80); do
    if ! kill -0 "$pid" 2>/dev/null; then
      printf '%s exited before becoming reachable.\n' "$label" >&2
      return 1
    fi
    if curl -fsS --max-time 1 "$url" >/dev/null 2>&1; then
      return 0
    fi
    sleep 0.25
  done
  printf '%s did not become reachable at %s\n' "$label" "$url" >&2
  return 1
}

API_PORT="$(free_port)"
WEB_PORT="$(free_port)"
(
  cd "$ROOT/apps/api"
  exec env \
    NUR_AI_PROVIDER=disabled \
    DATABASE_URL=postgresql+asyncpg://nur_app:unavailable@127.0.0.1:1/nur \
    REDIS_URL=redis://127.0.0.1:1/0 \
    "$ROOT/apps/api/.venv/bin/python" -m uvicorn app.main:app \
      --host 127.0.0.1 --port "$API_PORT" --log-level warning
) >"$RUNTIME/api.log" 2>&1 &
API_PID=$!
PIDS+=("$API_PID")
if ! wait_http API "http://127.0.0.1:$API_PORT/healthz" "$API_PID"; then
  cat "$RUNTIME/api.log" >&2
  exit 1
fi

(
  cd "$ROOT"
  if [[ "$BUILD_CHECKS" == "1" ]]; then
    exec npm --workspace apps/web run preview -- --host 127.0.0.1 --port "$WEB_PORT"
  fi
  exec npm --workspace apps/web run dev -- --host 127.0.0.1 --port "$WEB_PORT"
) >"$RUNTIME/web.log" 2>&1 &
WEB_PID=$!
PIDS+=("$WEB_PID")
if ! wait_http WEB "http://127.0.0.1:$WEB_PORT/" "$WEB_PID"; then
  cat "$RUNTIME/web.log" >&2
  exit 1
fi

if [[ "$BUILD_CHECKS" == "1" ]]; then
  printf 'APPLICATION_COLD_BOOT=PASS_API_HEALTHZ_AND_WEB_PREVIEW\n'
else
  printf 'APPLICATION_COLD_BOOT=PASS_API_HEALTHZ_AND_WEB_DEV\n'
fi
printf 'FULL_STACK_COLD_BOOT=NOT_RUN_REQUIRES_POSTGRES_REDIS\n'
printf 'WORKER_BEAT_READINESS=NOT_RUN_REQUIRES_REDIS_AND_DATABASE\n'
