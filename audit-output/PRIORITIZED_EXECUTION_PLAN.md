# PRIORITIZED EXECUTION PLAN

Ordered by dependency × ROI (security → proof → provider wiring → hardening).
No task modifies product code without founder approval where flagged.

---
### T1 — Rotate leaked OpenAI keys + regenerate archive  [SECURITY, do first]
- **Files:** none in Git. Archive `~/Downloads/NUR-TRUE-FULL-AUDIT-20260801-144301.tar.zst`; archive `.env.local`/`.env` in snapshots 04/06/07/08/09.
- **Intended behavior:** the 3 distinct live keys (F1) are invalidated; a re-staged archive contains **no** `.env`/`.env.local`.
- **Acceptance:** old keys 401 at `GET /v1/models`; new archive `grep -rl OPENAI_API_KEY` over extracted `.env*` = empty.
- **Tests:** `infra/scripts/secret-scan.sh`; manual archive re-scan.
- **Rollback:** n/a (rotation is forward-only).
- **Conflict risk:** none. **Founder approval:** not required (ops hygiene).

### T2 — Prove live Talk in THIS worktree (BLOCKED_EXTERNAL → PASS_CURRENT)  [depends: T1]
- **Files:** create `/home/nur/NUR-INTEGRATION-20260722/.env.local` (mode 600) via `infra/scripts/configure-openai-local.sh` with a **rotated** key. No source changes.
- **Intended behavior:** `RUN_NUR.sh openai` boots; `openai-smoke-local.sh` and `node infra/scripts/live-talk-two-turn-proof.mjs` PASS (two exact-reply turns + reload persistence).
- **Acceptance:** `LIVE_TALK_PASS_CURRENT`; smoke JSON `provider=openai, model_run_persisted, response_visible_after_refresh`.
- **Tests:** the three commands above.
- **Rollback:** `RUN_NUR.sh stop`; remove `.env.local`.
- **Conflict risk:** none (code already proven identical to snapshot 06). **Founder approval:** not required.

### T3 — Run the Playwright E2E suite in this worktree  [depends: T2]
- **Files:** none (test-only). `apps/web/e2e/*.spec.ts` (33 specs).
- **Intended behavior:** V197 reachability empirically confirmed (Talk, systems, community, projects, capsules, mobile/webkit, auth-recovery).
- **Acceptance:** green E2E run; convert matrix "LIVE_E2E (spec present)" to executed.
- **Tests:** `npx playwright test` against a booted stack.
- **Rollback:** n/a. **Conflict risk:** low. **Founder approval:** not required.

### T4 — Decide Teach NUR & Billing UI exposure  [product decision]
- **Files (if wiring):** `apps/web/src/bridge/*` + canonical V197 controls; `app/learning/routes.py`, `app/billing/routes.py` already exist.
- **Intended behavior:** either wire a V197 surface (BACKEND_ONLY→LIVE_E2E) or explicitly mark INTENTIONAL backend-only for P0.
- **Acceptance:** documented decision; if wired, E2E spec + green run.
- **Tests:** new E2E + existing backend suite.
- **Rollback:** revert bridge additions. **Conflict risk:** medium (touches canonical V197). **Founder approval: REQUIRED** (V197 presentation is immutable-by-mandate).

### T5 — Configure external providers for pilot  [depends: T4 for billing]
- **Files:** env/config only — Stripe/LemonSqueezy keys + webhook secret; email/push delivery providers.
- **Intended behavior:** Billing live (webhook verified), Notifications push/email on.
- **Acceptance:** billing webhook signature test against real provider; a delivered notification.
- **Tests:** `app/tests` billing/notification suites + a live webhook ping.
- **Rollback:** disable provider flags. **Conflict risk:** low. **Founder approval:** required (commercial).

### T6 — Minor hardening  [low priority]
- **Files:** `infra/scripts/bootstrap-dev.sh:99` (F3 sed delimiter); ensure prod seeding disabled (F2); add `.env*`, `celerybeat-schedule*`, `*.sqlite3` to archive-staging excludes.
- **Acceptance:** ruff/shellcheck clean; no runtime-state/secret files in future archives.
- **Tests:** re-run secret-scan + a staging dry-run.
- **Rollback:** revert. **Conflict risk:** none. **Founder approval:** not required.

---
## Dependency order
T1 → T2 → T3 → (T4 decision) → T5 ; T6 anytime.
ROI: T1 (eliminates active credential exposure) and T2 (unblocks every external
surface) are highest; T4/T5 gate paid tiers; T3 raises E2E confidence; T6 is polish.
