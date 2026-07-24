#!/usr/bin/env bash
# Deterministic NUR release gate runner (Masterplan V5 §26.5).
#
#   bash infra/scripts/nur-gate.sh <GATE>
#   bash infra/scripts/nur-gate.sh ALL
#   bash infra/scripts/nur-gate.sh --list
#
# Gates: G00_EVIDENCE … G16_FULL_RELEASE.
#
# Every run writes, per gate:
#   evidence/<timestamp>/<GATE>/result.json
#   evidence/<timestamp>/<GATE>/report.md
#   evidence/<timestamp>/<GATE>/<step>.log
#
# Each result records the commit, dirty-state manifest, environment class, start/end time,
# every command with its exit code, and a verdict. Verdicts are:
#
#   PASS                     every required step exited 0
#   FAIL                     a required step failed
#   BLOCKED_EXTERNAL         needs a credential, provider, or environment nobody here can supply
#   FOUNDER_ACTION_REQUIRED  needs a founder decision or account action
#   INCOMPLETE               everything that ran passed, but required checks are still unimplemented
#   NOT_IMPLEMENTED          the gate's checks do not exist yet, and saying so is the honest result
#
# A gate with no executable checks reports NOT_IMPLEMENTED. It never reports PASS by silence.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

RUN_STAMP="${NUR_GATE_STAMP:-$(date -u +%Y%m%dT%H%M%SZ)}"
EVIDENCE_ROOT="$ROOT/evidence/$RUN_STAMP"
COMMIT="$(git rev-parse HEAD 2>/dev/null || echo unknown)"
BRANCH="$(git branch --show-current 2>/dev/null || echo detached)"
ENV_CLASS="${NUR_ENV_CLASS:-local}"

GATES=(
  G00_EVIDENCE G01_STATIC G02_AUTH G03_V197 G04_PERFORMANCE G05_LIVE_AI G06_RECOVERY
  G07_INTELLIGENCE G08_REVENUE G09_GLOW G10_SYSTEMS G11_LANGUAGE G12_COMMUNITY
  G13_GROUP_RESEARCH G14_PROJECTS G15_SCALE_OPS G16_FULL_RELEASE
)

# --- per-gate state -----------------------------------------------------------------------
GATE_DIR=""
STEPS_JSON=""
GATE_FAILED=0
GATE_NOTES=""

json_escape() { python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))' <<<"$1"; }

note() { GATE_NOTES="${GATE_NOTES}${GATE_NOTES:+ | }$1"; }

# run <step-name> <command...> — required step; a non-zero exit fails the gate.
run() {
  local name="$1"; shift
  local log="$GATE_DIR/$name.log"
  local start; start="$(date -u +%s)"
  printf '$ %s\n\n' "$*" >"$log"
  "$@" >>"$log" 2>&1
  local code=$?
  local end; end="$(date -u +%s)"
  [ $code -ne 0 ] && GATE_FAILED=1
  STEPS_JSON="${STEPS_JSON}${STEPS_JSON:+,}$(printf '{"step":%s,"command":%s,"exit_code":%d,"seconds":%d,"log":%s}' \
    "$(json_escape "$name")" "$(json_escape "$*")" "$code" "$((end-start))" "$(json_escape "$name.log")")"
  printf '  %-34s exit=%-3d %ss\n' "$name" "$code" "$((end-start))"
  return $code
}

# skip <step-name> <reason> — records an unmet requirement without pretending it ran.
skip() {
  local name="$1" reason="$2"
  STEPS_JSON="${STEPS_JSON}${STEPS_JSON:+,}$(printf '{"step":%s,"command":null,"exit_code":null,"skipped_reason":%s}' \
    "$(json_escape "$name")" "$(json_escape "$reason")")"
  printf '  %-34s SKIPPED — %s\n' "$name" "$reason"
}

have() { command -v "$1" >/dev/null 2>&1; }

# --- gate bodies --------------------------------------------------------------------------
# Each gate_* function sets GATE_VERDICT_OVERRIDE when its honest verdict is not PASS/FAIL.

gate_G00_EVIDENCE() {
  run git_status git status --short
  run v197_integrity npm run --silent v197:integrity
  run secret_scan npm run --silent secret-scan
  local docs=(source-authority-report git-lineage-reconciliation conflict-and-supersession-report
              current-capability-gap-map founder-decisions credential-exposure-inventory)
  local missing=()
  for d in "${docs[@]}"; do
    [ -f "docs/v6/$d.md" ] || [ -f "docs/v6/$d.csv" ] || missing+=("$d")
  done
  if [ ${#missing[@]} -gt 0 ]; then
    GATE_FAILED=1; note "missing V6 documents: ${missing[*]}"
  fi
  # FD-001 ratified the canonical identity; rotation of the exposed archive keys is not proven.
  if grep -q "UNROTATED_P0" docs/v6/credential-exposure-inventory.csv 2>/dev/null; then
    GATE_VERDICT_OVERRIDE="FOUNDER_ACTION_REQUIRED"
    note "FOUNDER_ACTION_REQUIRED_ROTATE_OPENAI_KEYS — exposed archive keys not verified rotated"
  fi
}

gate_G01_STATIC() {
  run ruff apps/api/.venv/bin/ruff check apps/api
  run backend_tests bash -c 'cd apps/api && .venv/bin/python -m pytest -q'
  run alembic_single_head bash -c 'cd apps/api && ../../apps/api/.venv/bin/alembic heads | grep -c "(head)" | grep -qx 1'
  run web_typecheck npm run --silent web:typecheck
  run web_unit_tests npm run --silent web:test
  run web_build npm run --silent web:build
  run v197_integrity npm run --silent v197:integrity
  run secret_scan npm run --silent secret-scan
  run release_naming npm run --silent release:naming-scan
  run diff_check git diff --check
  if [ -f apps/mobile/package.json ]; then
    run mobile_typecheck npm run --silent mobile:typecheck
  else
    skip mobile_typecheck "apps/mobile is not present in this candidate"
  fi
  skip dependency_audit "no dependency-audit gate implemented yet (G01-009)"
  skip sbom "no SBOM generator implemented yet (G01-009)"
  skip migration_upgrade_from_populated "no populated-revision upgrade test yet (G01-014)"
  skip migration_downgrade "no downgrade execution test yet (G01-015)"
  skip fresh_extract_boot "fresh-clone/extract boot not wired into this runner yet (G01-017)"
}

playwright_ready() { [ -d "$HOME/.cache/ms-playwright" ] || [ -d "$ROOT/node_modules/playwright-core/.local-browsers" ]; }

api_ready() {
  curl -fsS --max-time 3 -o /dev/null "${NUR_API_ORIGIN:-http://localhost:8000}/healthz" 2>/dev/null
}

browser_gate() { # <spec...>
  if ! playwright_ready; then
    GATE_VERDICT_OVERRIDE="BLOCKED_EXTERNAL"
    note "Playwright browsers not installed — run: npx playwright install --with-deps"
    skip browser_suite "Playwright browsers unavailable"
    return
  fi
  # Playwright's webServer starts Vite only. Specs that exercise real auth proxy to
  # the API, so without it they fail with ECONNREFUSED — an environment gap, not a
  # product defect, and it must not be recorded as one.
  if ! api_ready; then
    GATE_VERDICT_OVERRIDE="BLOCKED_EXTERNAL"
    note "API not reachable at ${NUR_API_ORIGIN:-http://localhost:8000}/healthz — start the stack: bash RUN_NUR.sh"
    skip browser_suite "API stack not running"
    return
  fi
  run browser_suite npm --workspace apps/web run e2e -- "$@" --project=chromium-desktop --workers=1
}

gate_G02_AUTH() {
  run auth_backend_tests bash -c 'cd apps/api && .venv/bin/python -m pytest -q app/tests/test_auth.py app/tests/test_password_recovery.py'
  browser_gate e2e/fresh-signup.spec.ts e2e/landing-auth.spec.ts e2e/presentation-auth-recovery.spec.ts
  skip account_export_delete_e2e "export/delete surfaces not implemented (G02-014, G02-015)"
  skip session_management_ui "no session management surface (G02-013)"
}

gate_G03_V197() {
  run v197_integrity npm run --silent v197:integrity
  run control_matrix_regen node apps/web/scripts/rebuild-v197-control-matrix.mjs
  run control_matrix_fresh bash -c '[ "$(python3 -c "import json;print(json.load(open(\"docs/release/v197-control-matrix.json\"))[\"generated_from_sha\"])")" = "$(git rev-parse HEAD)" ]'
  run no_broken_controls bash -c 'python3 -c "
import json,sys
m=json.load(open(\"docs/release/v197-control-matrix.json\"))
bad={k:m[\"totals\"].get(k,0) for k in (\"DEAD\",\"DUPLICATE\",\"MISLEADING\")}
sys.exit(1 if any(bad.values()) else 0)"'
  browser_gate e2e/v197-control-matrix.spec.ts e2e/v197-host-parity.spec.ts e2e/v197-forensic-shell.spec.ts e2e/v197-runtime-lifecycle.spec.ts
  skip deferred_controls "7 controls remain NOT_IMPLEMENTED_VISIBLE (G03-007)"
  skip backend_only_surfaces "Personal Memory, Teach NUR and Billing unreachable from V197 (G03-008..010)"
}

gate_G04_PERFORMANCE() {
  browser_gate e2e/v197-performance-acceptance.spec.ts e2e/v197-performance.spec.ts e2e/v197-responsive-accessibility.spec.ts
  skip named_reference_devices "reference device/browser tier not declared (G04-008, G04-009)"
  skip heap_soak "10-minute heap/listener/observer soak not implemented (G04-004)"
}

gate_G05_LIVE_AI() {
  run provider_contract_tests bash -c 'cd apps/api && .venv/bin/python -m pytest -q app/tests/test_ai_provider_failures.py app/tests/test_ai_structured_outputs.py app/tests/test_verifier_grounding.py app/tests/test_cognition_streaming.py'
  run secret_scan npm run --silent secret-scan
  if [ ! -f "$ROOT/.env.local" ]; then
    GATE_VERDICT_OVERRIDE="FOUNDER_ACTION_REQUIRED"
    note "FOUNDER_ACTION_REQUIRED_CONFIGURE_OPENAI — no .env.local on this candidate; a proof from another worktree must not be inherited"
    skip live_two_turn_proof "no server-side provider credential configured here"
  else
    run live_two_turn_proof node infra/scripts/live-talk-two-turn-proof.mjs
  fi
  skip budget_enforcement "per-user/plan/mode/global budgets not implemented (G05-013)"
}

gate_G06_RECOVERY() {
  run recovery_tests bash -c 'cd apps/api && .venv/bin/python -m pytest -q app/tests/test_password_recovery.py'
  GATE_VERDICT_OVERRIDE="FOUNDER_ACTION_REQUIRED"
  note "FOUNDER_ACTION_REQUIRED_CONFIGURE_EMAIL_PROVIDER — local file capture is development-only"
  skip production_delivery "no transactional email adapter configured (G06-001)"
  skip retry_dedup_bounce "delivery retry/dedup/bounce not implemented (G06-004)"
}

gate_G07_INTELLIGENCE() {
  run intelligence_tests bash -c 'cd apps/api && .venv/bin/python -m pytest -q app/tests/test_live_intelligence.py app/tests/test_intelligence_contracts.py app/tests/test_personal_memory.py app/tests/test_teach_nur.py app/tests/test_omega.py app/tests/test_rls.py'
  skip eval_suite "packages/evals does not exist; no multilingual/adversarial regression harness (G07-013)"
  skip tool_registry "no bounded tool registry with confirmation rules (G07-012)"
  skip whole_chain_runtime "no single runtime proof of the full Talk->Return->why-changed cycle (G07-001)"
}

gate_G08_REVENUE() {
  run billing_tests bash -c 'cd apps/api && .venv/bin/python -m pytest -q app/tests/test_billing.py app/tests/test_feature_lock_endpoints.py'
  GATE_VERDICT_OVERRIDE="FOUNDER_ACTION_REQUIRED"
  note "FOUNDER_ACTION_REQUIRED_CONFIGURE_BILLING_TEST_PROVIDER"
  skip provider_test_mode "no billing provider configured (G08-002)"
  skip billing_ui "no billing control in the V197 matrix (G08-006)"
}

gate_G09_GLOW() {
  run glow_tests bash -c 'cd apps/api && .venv/bin/python -m pytest -q app/tests/test_notifications.py app/tests/test_sol_living_system.py'
  skip fraud_detection "no Glow fraud detection (G09-006)"
  skip leaderboards "no leaderboard implementation (G09-011)"
  skip notification_delivery "no push/email delivery adapter (G09-014)"
  skip experiment_engine "no experiment engine (G09-015)"
}

gate_G10_SYSTEMS() {
  run systems_tests bash -c 'cd apps/api && .venv/bin/python -m pytest -q app/tests/test_sol_living_system.py app/tests/test_live_universe.py app/tests/test_product_surfaces.py'
  browser_gate e2e/sol-living-v197.spec.ts e2e/universe-lenses.spec.ts
  skip per_system_vertical_slice "no per-System diagnostic->action->Return->projection proof (G10-sys1..7)"
}

gate_G11_LANGUAGE() {
  run translation_tests bash -c 'cd apps/api && .venv/bin/python -m pytest -q app/tests/test_translations.py'
  skip catalog_completeness "no key-completeness validator (G11-003)"
  skip locale_slots_35 "35 locale slots not present (G11-004)"
  skip string_extraction "no zero-raw-string extraction test (G11-002)"
  GATE_VERDICT_OVERRIDE="FOUNDER_ACTION_REQUIRED"
  note "FOUNDER_ACTION_REQUIRED_LOCALE_HUMAN_REVIEW — an agent may not label its own output native-reviewed"
}

gate_G12_COMMUNITY() {
  run community_tests bash -c 'cd apps/api && .venv/bin/python -m pytest -q app/tests/test_community_completion.py app/tests/test_group_nur.py app/tests/test_rls.py'
  browser_gate e2e/community-group-nur.spec.ts
  skip realtime_gateway "no authenticated realtime gateway (G12-006)"
  skip signal_feed "no feed ranking module (G12-011)"
  skip anti_abuse "no anti-abuse suite (G12-013)"
}

gate_G13_GROUP_RESEARCH() {
  run group_research_tests bash -c 'cd apps/api && .venv/bin/python -m pytest -q app/tests/test_group_research_completion.py app/tests/test_consultations.py app/tests/test_group_nur.py'
  GATE_VERDICT_OVERRIDE="BLOCKED_EXTERNAL"
  note "research live fetch is BLOCKED_BY_EXTERNAL_PROVIDER in the control matrix"
  skip live_research "no lawful research provider configured (G13-005)"
  skip expert_module "no expert verification module (G13-009)"
}

gate_G14_PROJECTS() {
  run project_tests bash -c 'cd apps/api && .venv/bin/python -m pytest -q app/tests/test_am_projects.py app/tests/test_am_project_execution.py app/tests/test_am_project_storage.py app/tests/test_am_project_quota.py app/tests/test_am_project_recovery.py app/tests/test_capsules.py app/tests/test_storage_hygiene.py'
  browser_gate e2e/project-deliverables.spec.ts e2e/capsule.spec.ts
  skip bounded_agents "no agents module: tasks/runs/artifacts/reviews/permissions/budgets (G14-008..010)"
}

gate_G15_SCALE_OPS() {
  run ops_tests bash -c 'cd apps/api && .venv/bin/python -m pytest -q app/tests/test_health.py app/tests/test_ops_diagnostics.py app/tests/test_dr.py app/tests/test_bounded_load.py'
  GATE_VERDICT_OVERRIDE="FOUNDER_ACTION_REQUIRED"
  note "FOUNDER_ACTION_REQUIRED_STAGING_ACCESS — no staging environment, no CI run on this candidate"
  skip staging_deploy "no staging environment (G15-008)"
  skip timed_restore_drill "restore drill not executed with measured RPO/RTO (G15-013)"
  skip privacy_center "no privacy center (G15-019)"
}

gate_G16_FULL_RELEASE() {
  GATE_VERDICT_OVERRIDE="FOUNDER_ACTION_REQUIRED"
  note "FOUNDER_ACTION_REQUIRED_RELEASE_APPROVAL — and G00..G15 are not all PASS"
  skip all_gates_pass "prerequisite gates are not all PASS (G16-002)"
  skip package_release "infra/scripts/package-release.sh not implemented (G16-012)"
  skip verify_release_package "infra/scripts/verify-release-package.sh does not exist (G16-013)"
  skip sbom "no SBOM generator (G16-006)"
  skip status_ledger_v6 "docs/v6/NUR_EXACT_STATUS_LEDGER_V6.md not authored (G16-011)"
}

# --- driver -------------------------------------------------------------------------------
run_gate() {
  local gate="$1"
  GATE_DIR="$EVIDENCE_ROOT/$gate"
  mkdir -p "$GATE_DIR"
  STEPS_JSON=""; GATE_FAILED=0; GATE_NOTES=""; GATE_VERDICT_OVERRIDE=""
  local started; started="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  printf '\n=== %s ===\n' "$gate"

  "gate_$gate"

  local ended; ended="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  # A skipped step is an unmet requirement, so it can never round up to PASS.
  # Without this, a gate whose one runnable check passes would report PASS while
  # four requirements sat unimplemented — a fake PASS by omission.
  local skipped=0
  case "$STEPS_JSON" in *'"skipped_reason"'*) skipped=1 ;; esac

  local verdict
  if [ "$GATE_FAILED" -ne 0 ]; then
    verdict="FAIL"
  elif [ -n "$GATE_VERDICT_OVERRIDE" ]; then
    verdict="$GATE_VERDICT_OVERRIDE"
  elif [ -z "$STEPS_JSON" ]; then
    verdict="NOT_IMPLEMENTED"
  elif [ "$skipped" -ne 0 ]; then
    verdict="INCOMPLETE"
  else
    verdict="PASS"
  fi

  local dirty; dirty="$(git status --porcelain | head -200)"
  python3 - "$GATE_DIR" "$gate" "$verdict" "$started" "$ended" "$COMMIT" "$BRANCH" "$ENV_CLASS" \
           "$GATE_NOTES" "$dirty" "[$STEPS_JSON]" <<'PY'
import json, sys, pathlib
d, gate, verdict, started, ended, commit, branch, env, notes, dirty, steps = sys.argv[1:12]
steps = json.loads(steps)
result = {
    "gate": gate, "verdict": verdict, "commit": commit, "branch": branch,
    "environment_class": env, "started_at": started, "ended_at": ended,
    "dirty_state_manifest": [l for l in dirty.splitlines() if l.strip()],
    "steps": steps, "notes": notes or None,
}
p = pathlib.Path(d)
(p / "result.json").write_text(json.dumps(result, indent=2) + "\n")
lines = [f"# {gate} — {verdict}", "",
         f"- commit: `{commit}`", f"- branch: `{branch}`",
         f"- environment: `{env}`", f"- window: {started} → {ended}",
         f"- dirty entries: {len(result['dirty_state_manifest'])}", ""]
if notes:
    lines += ["## Notes", "", notes, ""]
lines += ["## Steps", "", "| step | exit | seconds | log |", "| --- | --- | --- | --- |"]
for s in steps:
    if s.get("command") is None:
        lines.append(f"| {s['step']} | skipped | — | {s.get('skipped_reason','')} |")
    else:
        lines.append(f"| {s['step']} | {s['exit_code']} | {s.get('seconds','')} | `{s['log']}` |")
lines.append("")
(p / "report.md").write_text("\n".join(lines))
print(f"  -> {verdict}  ({d}/result.json)")
PY
  [ "$verdict" = "PASS" ] && return 0 || return 1
}

case "${1:-}" in
  --list|"") printf '%s\n' "${GATES[@]}"; exit 0 ;;
  ALL)
    mkdir -p "$EVIDENCE_ROOT"
    overall=0
    for g in "${GATES[@]}"; do run_gate "$g" || overall=1; done
    printf '\n=== SUMMARY (%s) ===\n' "$RUN_STAMP"
    for g in "${GATES[@]}"; do
      printf '%-22s %s\n' "$g" "$(python3 -c "import json;print(json.load(open('$EVIDENCE_ROOT/$g/result.json'))['verdict'])")"
    done
    printf '\nevidence: %s\n' "$EVIDENCE_ROOT"
    exit $overall ;;
  *)
    for g in "${GATES[@]}"; do
      if [ "$g" = "$1" ]; then mkdir -p "$EVIDENCE_ROOT"; run_gate "$g"; exit $?; fi
    done
    echo "unknown gate: $1" >&2
    printf '%s\n' "${GATES[@]}" >&2
    exit 2 ;;
esac
