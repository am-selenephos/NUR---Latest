# NUR Final Closure Implementation Plan

> **Execution contract:** `NUR_FULLSTACK_AGENTEND_MASTER_ADDENDUM_20260814.md`
> plus the founder's 2026-08-21 final-closure directive.

**Goal:** Close every internally solvable Addendum requirement on one exact
commit without replacing V197, weakening owner isolation, or inventing external
provider evidence.

**Architecture:** Keep V197 as the only visible product and FastAPI as the only
public trust boundary. PostgreSQL remains durable authority; Redis/Celery remain
transport. Consolidate duplicate cognitive authorities before adding release
proof, then exercise the existing product through a same-origin production web
host and deterministic two-owner real-stack browser harness.

## Workstream 1: Canonical cognitive authority

**Files:**
- Modify: `apps/api/app/omega/claim_service.py`
- Modify: `apps/api/app/omega/why_changed_service.py`
- Modify: `apps/api/app/mind/why_changed.py`
- Delete: `apps/api/app/mind/beliefs.py`
- Modify: `apps/api/app/tests/test_beliefs_attention_phase3.py`
- Modify: `apps/api/app/tests/test_omega.py`
- Modify: `apps/api/app/tests/test_intelligence_contracts.py`

1. Write failing database tests proving every Omega claim transition writes and
   reads the canonical append-only WhyChanged ledger, with owner isolation.
2. Run the targeted tests and confirm the expected red failure.
3. Record claim creation/confirmation/correction/retirement through
   `mind.why_changed.WhyChangedService`; retain evidence-edge summaries only as
   evidence projection.
4. Remove the unused in-memory belief lifecycle and its isolated tests; retain
   durable `SemanticClaim` + `ClaimEvidence` as the Mind belief authority.
5. Run targeted and full API suites.

## Workstream 2: Independent Brain evaluation and governed research

**Files:**
- Modify: `apps/api/app/brain/evaluation.py`
- Modify: `apps/api/app/brain/research.py`
- Add: `apps/api/app/brain/fixtures/evaluation-corpus-v2.json`
- Modify: `apps/api/app/tests/test_addendum_dg_contracts.py`
- Add/modify targeted Brain evaluation and research tests.

1. Write failing tests requiring a frozen corpus with explicit negative cases,
   immutable version/hash, and observations produced independently from expected
   labels.
2. Add a provider-neutral, server-only retrieval adapter contract with bounded
   scope and fail-closed provenance; keep live retrieval explicitly external.
3. Verify held-out/shadow promotion fails on missing, erroneous, or mismatched
   observations and passes only the frozen corpus.

## Workstream 3: Production web serving

**Files:**
- Modify: `apps/web/Dockerfile`
- Add: `apps/web/nginx.conf`
- Modify: `docker-compose.yml`
- Add/modify: `infra/tests/production-web-serving.test.sh`
- Modify: `.github/workflows/readiness.yml`

1. Add a failing topology contract test proving the final image serves built
   static assets and proxies same-origin `/api` to FastAPI.
2. Replace the development-server image with a multi-stage Vite build and a
   static reverse-proxy runtime.
3. Preserve SPA fallback, immutable asset caching, session cookies, CSRF origin,
   and V197 asset paths.
4. Boot the full compose stack and verify `/`, `/api/v1/healthz`,
   `/api/v1/readyz`, and `/api/v1/metrics` through the web origin.

## Workstream 4: Deterministic real-stack product proof

**Files:**
- Add: `apps/web/e2e/helpers/realStack.ts`
- Add: `apps/web/e2e/nur-real-stack-routes.spec.ts`
- Add: `apps/web/playwright.real-stack.config.ts`
- Modify route/API code only when a real failing lifecycle proves a mismatch.

1. Provision isolated PostgreSQL/Redis/API/worker/Beat/web and two owner
   accounts without intercepting application requests.
2. Prove B6 and C1-C5 through V197 controls, including replay, cancel,
   proposal, APPROVE/EDIT/REJECT, outbox, worker completion, reload, and owner
   denial.
3. Exercise all 18 Phase-H surfaces for render, canonical read/write behavior,
   reload, empty/error state, mobile, keyboard, and accessibility.
4. Run the Capsule grant/use/revoke flow ten consecutive clean no-retry cycles;
   stop on first failure and capture trace before fixing.

## Workstream 5: Browser quality and security

**Files:**
- Add/modify focused Playwright accessibility, WebKit, reduced-motion, and
  performance specs.
- Modify: `infra/scripts/generate-mutation-security-matrix.py` only if a real
  uncovered mutation is found.

1. Run Chromium desktop/mobile and Linux WebKit with axe-equivalent checks,
   keyboard traversal, focus, dialogs, RTL overflow, and touch targets.
2. Measure Entry, Universe, Systems, Talk, Agents, Insights, and Map; prove one
   galaxy owner, one Star Brain owner, paused hidden routes, and one RAF owner.
3. Run malicious-evidence cases and prove no policy, memory, tool, approval, or
   owner-state authority transfer.

## Workstream 6: Runtime and release evidence

**Files:**
- Modify release/DR scripts only when execution exposes a root cause.
- Generate SHA-bound evidence under `docs/completion/evidence/`.
- Regenerate Node and Python CycloneDX SBOMs for the candidate SHA.

1. Run exact-SHA cold boot and graceful shutdown.
2. Run isolated DB/object backup and restore parity with revision, hashes,
   critical IDs, owner state, RPO, and RTO.
3. Execute real-process crash scenarios A-D and record PIDs, timestamps,
   workflow/step/outbox/idempotency state, restart, final state, and duplicate
   effect count.
4. Package and independently verify a fresh-extract HOLD artifact with zero
   missing/extra/hash/size/traversal/symlink/duplicate/secret/V197 failures.

## Workstream 7: Final evidence, review, and GitHub

**Files:**
- Update: `docs/completion/CODEX_CURRENT_COMPLETION_20260821.md`
- Add/update: `docs/completion/CODEX_FINAL_CLOSURE_LEDGER_20260821.md`
- Add: `docs/completion/CODEX_RESEARCH_LOG_20260821.md`
- Add: `docs/completion/CODEX_TEST_EVIDENCE_20260821.md`
- Add: `docs/completion/CODEX_FINAL_ADDENDUM_MATRIX_20260821.csv`
- Add: `docs/completion/CODEX_FINAL_ADDENDUM_MATRIX_20260821.md`
- Update: `docs/completion/INDEPENDENT_REVIEW_PACKET.md`

1. Run the complete deterministic release gate once on the exact candidate
   commit and record complete outputs and counts.
2. Request an independent code/security/release review and resolve every
   critical or important internal finding.
3. Commit scoped changes, push the closure branch, refresh draft PR #5, and
   verify required CI on the exact pushed SHA.
4. Keep live provider, human localization quality, macOS Safari, merge, main
   CI, final release artifact, tag, and repository rename honestly classified
   until their external/founder gates are available.
