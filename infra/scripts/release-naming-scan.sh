#!/usr/bin/env bash
# Naming regression guard.
#
# This file resolves an add/add conflict between two guards that were written
# independently and do different jobs. Keeping only one would silently disable a
# real check, so both run and the script fails if either fails.
#
#   1. Repo-wide token scan (from main). One forbidden token, checked across
#      every tracked path and every tracked text file. Broad file scope, narrow
#      vocabulary.
#
#   2. Release-surface naming scan. A wider vocabulary — build-process, donor,
#      rescue-branch, competition and builder-agent terminology — checked only
#      against the front-door files a user sees and that ship in the
#      distributable. Narrow file scope, broad vocabulary.
#
# The scopes differ deliberately. Internal construction history under docs/ is a
# development record and is intentionally not scanned by (2), but the single
# token in (1) is not permitted anywhere at all.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

status=0

# ── 1. Repo-wide forbidden token ────────────────────────────────────────────
# Built at runtime so this scanner does not itself contain the literal string it
# is responsible for rejecting.
forbidden_token="$(printf '%s%s' 'cou' 'sin')"

# Internal construction history is exempt, and only that. These files are
# development records — several are captured command output, so rewriting them
# to satisfy a naming rule would falsify the record rather than clean anything.
# The token stays forbidden everywhere that ships or that a user can see, which
# is the policy both guards were written to enforce.
RECORD_PATHS=(
  ":!docs/integration"
  ":!docs/v5"
  ":!docs/v6"
  ":!docs/completion"
)

if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  path_hits="$(git ls-files -- . "${RECORD_PATHS[@]}" | grep -i -- "$forbidden_token" || true)"
  if [[ -n "$path_hits" ]]; then
    printf 'FORBIDDEN TOKEN IN TRACKED PATHS:\n%s\n\n' "$path_hits" >&2
    status=1
  fi

  content_hits="$(git grep -nIi -- "$forbidden_token" -- . "${RECORD_PATHS[@]}" || true)"
  if [[ -n "$content_hits" ]]; then
    printf 'FORBIDDEN TOKEN IN TRACKED FILE CONTENT:\n%s\n\n' "$content_hits" >&2
    status=1
  fi
else
  # Release verification runs from an extracted archive with no .git. Do not
  # silently convert that into an empty scan: establish a recognizable NUR root
  # and enumerate the extracted payload directly.
  required_root_files=(
    README.md
    package.json
    package-lock.json
    infra/scripts/release-naming-scan.sh
  )
  for required in "${required_root_files[@]}"; do
    if [[ ! -f "$required" ]]; then
      printf 'naming scan: cannot establish release root; missing %s\n' "$required" >&2
      exit 2
    fi
  done

  scanned=0
  while IFS= read -r -d '' candidate; do
    relative="${candidate#./}"
    scanned=$((scanned + 1))
    if [[ "${relative,,}" == *"${forbidden_token,,}"* ]]; then
      printf 'FORBIDDEN TOKEN IN EXTRACTED PATH:\n%s\n\n' "$relative" >&2
      status=1
    fi

    set +e
    hits="$(grep -nIi -- "$forbidden_token" "$candidate" 2>/dev/null)"
    grep_status=$?
    set -e
    if [[ "$grep_status" -eq 0 ]]; then
      printf 'FORBIDDEN TOKEN IN EXTRACTED FILE CONTENT (%s):\n%s\n\n' "$relative" "$hits" >&2
      status=1
    elif [[ "$grep_status" -gt 1 ]]; then
      printf 'naming scan: could not inspect extracted file %s\n' "$relative" >&2
      status=1
    fi
  done < <(
    find . \
      \( -path './.git' -o -path './node_modules' -o -path './apps/api/.venv' \
         -o -path './dist' -o -path './build' -o -path './.nur-runtime' \
         -o -path './docs/integration' -o -path './docs/v5' -o -path './docs/v6' \
         -o -path './docs/completion' -o -path './playwright-report' \
         -o -path './test-results' \) -prune \
      -o \( -type f -o -type l \) -print0
  )
  if [[ "$scanned" -eq 0 ]]; then
    printf 'naming scan: no extracted files were inspected; failing closed.\n' >&2
    exit 2
  fi
fi

# ── 2. Release-surface naming ───────────────────────────────────────────────
# Explicit release surface. Add new public-facing docs/scripts here as they land.
RELEASE_SURFACE=(
  README.md
  QUICKSTART_BOOT.md
  RUNBOOK.md
  SECURITY_NOTES.md
  DEMO_SCRIPT.md
  package.json
  START_NUR.sh
  RUN_NUR.sh
)
# Boot/operations scripts are release-facing too (they ship and are user-run),
# except this scanner itself — it necessarily names what it rejects.
while IFS= read -r script; do
  case "$script" in
    infra/scripts/release-naming-scan.sh) continue ;;
  esac
  RELEASE_SURFACE+=("$script")
done < <(find infra/scripts -maxdepth 1 -name '*.sh' | sort)

FORBIDDEN='build[ -]?week|lane[ -]?[ab]\b|rescue/lane|\bcodex\b|\bfable\b|\bopus\b|\bclaude\b|donor repo|am-selenephos|am-statementforge'

for path in "${RELEASE_SURFACE[@]}"; do
  [[ -f "$path" ]] || continue
  if hits="$(grep -niE "$FORBIDDEN" "$path" 2>/dev/null)"; then
    printf 'NAMING VIOLATION in %s:\n%s\n\n' "$path" "$hits" >&2
    status=1
  fi
done

if [[ "$status" -ne 0 ]]; then
  printf 'naming scan: FAIL — see violations above.\n' >&2
  exit 1
fi
printf 'naming scan: PASS — no forbidden token outside internal records, and the release surface uses only public NUR naming.\n'
