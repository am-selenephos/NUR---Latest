#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

if ! command -v rg >/dev/null 2>&1; then
  printf "Secret scan cannot run: ripgrep (rg) is required.\n" >&2
  exit 2
fi

PATTERN='sk-(proj-)?[A-Za-z0-9_-]{20,}|(OPENAI_API_KEY|VITE_OPENAI_API_KEY|NEXT_PUBLIC_OPENAI_API_KEY)[[:space:]]*=[[:space:]]*[^[:space:]#]+|Authorization:[[:space:]]*Bearer[[:space:]]+[^[:space:]]+'

scan_tree() {
  local label="$1"
  shift
  if [[ "$#" -eq 0 ]]; then
    return 0
  fi
  if rg -n --hidden --pcre2 "$PATTERN" "$@" \
    --glob '!node_modules/**' \
    --glob '!**/node_modules/**' \
    --glob '!.venv/**' \
    --glob '!**/.venv/**' \
    --glob '!.git/**' \
    --glob '!.env' \
    --glob '!.env.*' \
    --glob '!*.sha256' \
    --glob '!infra/scripts/secret-scan.sh'
  then
    printf "Secret scan failed in %s.\n" "$label" >&2
    exit 1
  fi
}

SOURCE_PATHS=()
for path in apps packages infra .github package.json package-lock.json pyproject.toml .env.example .dockerignore .gitignore; do
  [[ -e "$path" ]] && SOURCE_PATHS+=("$path")
done
scan_tree "tracked source" "${SOURCE_PATHS[@]}"

if [[ -d apps/web/dist ]]; then
  scan_tree "frontend dist" apps/web/dist
fi
if [[ -d playwright-report ]]; then
  scan_tree "playwright report" playwright-report
fi
if [[ -d test-results ]]; then
  scan_tree "playwright traces" test-results
fi
if [[ -d logs ]]; then
  scan_tree "logs" logs
fi
if [[ -d proof ]]; then
  scan_tree "generated proof artifacts" proof
fi
if [[ -d evidence ]]; then
  scan_tree "generated evidence artifacts" evidence
fi

printf "Secret scan passed: no OpenAI key, bearer token, or key assignment pattern found in scanned artifacts.\n"
