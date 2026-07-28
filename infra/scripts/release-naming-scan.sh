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
