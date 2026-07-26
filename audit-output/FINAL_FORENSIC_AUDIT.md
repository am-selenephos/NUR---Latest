# NUR — FINAL FORENSIC AUDIT

Read-only forensic audit of the full NUR corpus vs current Git.
Date: 2026-07-24 · Auditor: Fable (read-only mode) · No product code modified.

## 1. Scope executed
- Current repo `/home/nur/NUR-INTEGRATION-20260722` @ `6d7eeef`
  (branch `release/nur-p0-candidate`, tag `nur-p0-rc1`).
- Archive `NUR-TRUE-FULL-AUDIT-20260801-144301.tar.zst` (SHA-256 verified) →
  3,964 files, 10 snapshots, 13 git bundles, 2 lane tarballs.

## 2. Coverage (independently recomputed, not trusted)
| Metric | Value |
|---|---|
| Total files | 3,964 (ledger rows = 3,964, exact) |
| Unique contents | 913 (791 text / 122 binary) |
| Unique repo hashes | 885 (matches archive manifest, 0 diff) |
| Failures / unresolved | 0 / 0 |
All text handled by direct read (current repo + core historical bundles) or proven
byte-identity to a reviewed canonical. All binaries inspected (bundles verified,
sqlite schemas read, screenshots viewed, fonts identified).

## 3. Integration truth
- Current Git = **integration baseline `7a56510` + 1 Live-Talk commit `6d7eeef`**.
- **All 470 current tracked files are byte-present in the archive** (464 unchanged
  from baseline + 6 Live-Talk files == snapshot 06). Zero current file differs from
  all archive versions.
- 8 lanes reconciled: 7 are direct ancestors of HEAD; **Lane B (G10-G15)** was
  content-integrated (its 4 tip commits map to `dfa20bd/28f23e5/72c747c/85883b1`;
  migrations renumbered 0022-0024 → 0027-0029, features present).
- **No stranded production feature.** Only archive-only modern paths: 3 renumbered
  (present) migrations + intentionally-removed `build-week-gate.sh` + proof
  screenshots. Snapshots 09 (mental-health chatbot) and 10 (React skin) are
  superseded prior generations, correctly excluded.

## 4. Live-Talk (`6d7eeef` vs proven state)
The 6 proven files are **byte-identical** to snapshot 06 (the worktree that
achieved a real LIVE_TALK_PASS) and differ from baseline exactly by the gpt-4.1
fixes (reasoning-effort gate; verbatim kind:id citation contract; CSS/venv/smoke).
`6d7eeef` is the FINAL proven set, not an intermediate.

## 5. Current-worktree gates (executed here, nothing inherited)
Backend regression **180 passed**; frontend unit **63 passed**; Talk-critical DB
tests **17 passed**; ruff **clean**; alembic **single head 0030**; secret-scan
**clean**; `git diff --check` **clean**; typecheck **clean**; reasoning-effort gate
**verified**. Live OpenAI Talk gate: **LIVE_TALK_BLOCKED_EXTERNAL** — no server-only
key in this worktree (not inherited from the other worktree).

## 6. Product reachability
19 features mapped; weighted UI-reachability **≈85%**. 11 LIVE_E2E (spec+wiring+
backend-green), Talk BLOCKED_EXTERNAL, password-recovery INTENTIONAL_LOCAL_ONLY,
3 PARTIAL, 3 BACKEND_ONLY (Personal-memory surface, Teach NUR, Billing).

## 7. Security
Strong current-code posture (RLS txn-local + tested isolation, CSRF double-submit,
SecretStr, constant-time webhook HMAC, no synthetic-success, path-traversal guard,
prompt-logging off). **One HIGH issue: F1 — 3 live OpenAI keys leaked in the archive
`.env.local`/`.env` (snapshots 04/06/07/08/09).** Current Git is clean; the leak is
archive/backup hygiene. Rotate keys + regenerate archive without dotfiles.

## 8. Verdict
Code is release-candidate quality. GO for LOCAL_DEVELOPMENT; GO_WITH_CONDITIONS for
FOUNDER_DEMO and CONTROLLED_BETA; HOLD for PAID_PILOT and PUBLIC_* pending
operational gates (rotate keys, configure OpenAI/Stripe here, run live Talk +
Playwright E2E). See RELEASE_VERDICT.md and PRIORITIZED_EXECUTION_PLAN.md.

## Report index
00_CURRENT_GIT_STATE.md · 01_ARCHIVE_INTEGRITY.md · FILE_LEDGER.csv ·
READ_COVERAGE.md · PATH_VERSION_MATRIX.csv · SNAPSHOT_COMPARISON.md ·
STRANDED_IMPLEMENTATIONS.md · GIT_LANE_RECONCILIATION.csv · GIT_HISTORY_REPORT.md ·
CURRENT_GIT_FILE_VERDICT.csv · CURRENT_GIT_GAP_REPORT.md ·
LIVE_TALK_PORT_COMPARISON.md · CURRENT_GIT_TEST_EVIDENCE.md ·
FEATURE_REACHABILITY_MATRIX.csv · PRODUCT_COMPLETION_REPORT.md ·
SECURITY_PRIVACY_REPORT.md · FINAL_FORENSIC_AUDIT.md · RELEASE_VERDICT.md ·
PRIORITIZED_EXECUTION_PLAN.md · ALL_PATHS.txt · ALL_SHA256.txt ·
current-working-tree.patch · current-index.patch · CURRENT_TRACKED_MANIFEST.txt
