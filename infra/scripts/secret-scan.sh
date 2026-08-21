#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

if ! command -v rg >/dev/null 2>&1; then
  printf "Secret scan cannot run: ripgrep (rg) is required.\n" >&2
  exit 2
fi

# Match credential formats rather than variable names alone. The lookbehind
# prevents ordinary prose such as "risk-management" from looking like an
# OpenAI key while still catching keys embedded in JSON, logs and bundles.
PATTERN='(?<![A-Za-z0-9])sk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|AKIA[0-9A-Z]{16}|ASIA[0-9A-Z]{16}|xox[baprs]-[A-Za-z0-9-]{10,}|sk_live_[A-Za-z0-9]{16,}|rk_live_[A-Za-z0-9]{16,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|Authorization:[[:space:]]*Bearer[[:space:]]+[^[:space:]"'"'"'<>]+'

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
    --glob '!.env.local' \
    --glob '!*.sha256' \
    --glob '!infra/scripts/secret-scan.sh'
  then
    printf "Secret scan failed in %s.\n" "$label" >&2
    exit 1
  fi
}

SOURCE_PATHS=()
for path in apps packages infra .github docs contracts package.json package-lock.json pyproject.toml .env.example .dockerignore .gitignore; do
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
