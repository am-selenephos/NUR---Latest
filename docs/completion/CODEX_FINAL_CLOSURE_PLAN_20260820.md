# NUR Final Closure Plan - 2026-08-20

## Objective

Close every internally solvable requirement from the NUR Fullstack Agentend
Master Addendum and the Final HOLD Takeover on one exact commit. Preserve the
canonical V197 presentation and trust boundaries. Keep external provider and
founder gates explicitly blocked rather than simulating success.

## Authority Order

1. Current repository behavior and tests on the exact branch SHA.
2. `NUR_FULLSTACK_AGENTEND_MASTER_ADDENDUM_20260814.md` for architecture,
   ownership, persistence, agentend, security, and release laws.
3. `CODEX TAKEOVER - NUR FINAL HOLD -> TRUE FULL PASS` for the final closure
   delta and evidence requirements.
4. Existing completion matrices as historical inputs, never as proof by
   themselves.

The takeover narrows the final queue; it does not replace the addendum's system
laws.

## Baseline

- Repository: `am-selenephos/NUR---Latest`
- Branch point: `origin/main`
- Baseline SHA: `1c6f5f1e9f3380204f6809d2a78364e046e4908e`
- Closure branch: `codex/nur-final-closure-20260820`
- Exact-main readiness run: `32368838307` (historical green evidence; rerun is
  required after changes)
- Repository-wide Ruff on the baseline: zero findings with Ruff `0.15.22`.
  The takeover's approximately 416 findings are stale and must not be treated
  as current product defects.

## Execution

### 1. Reconcile evidence

- Recompute requirement counts from the repository, tests, migrations, and
  live receipts.
- Classify every unresolved row as product work, evidence-only, external, or a
  founder decision.
- Reconcile the 22 commits on the older integration branch as
  `ALREADY_PRESENT`, `SUPERSEDED`, `UNIQUE_PORT`, `CONFLICT`, `STALE`, or
  `DEAD`; never cherry-pick the branch wholesale.

### 2. Close Capsule lifecycle

- Run the live two-account Playwright lifecycle with one worker and no retries.
- Repeat from clean state to establish whether the failure is deterministic or
  intermittent.
- Fix the first proven root cause only. Do not weaken assertions, force clicks,
  add sleeps, or inflate timeouts.

### 3. Close backend and agentend gaps

- Port only missing governed outcome-learning behavior from the older branch,
  with current-main tests first.
- Verify owner isolation, RLS, idempotency, correction/dispute invalidation,
  agent-verifier feedback, and no model self-modification.
- Reconcile mutation, injection, capability, Brain, Talk, Insights, and worker
  changes against current equivalents before editing.

### 4. Prove runtime recovery

- Start real API, worker, and beat processes against isolated local services.
- Kill and restart controlled processes for the exact required scenarios.
- Prove idempotent completion, no duplicate side effects, and persisted
  recovery state. Save machine-readable and human-readable receipts.

### 5. Rebuild final authority artifacts

- Final requirement matrix and CSV.
- Final gate status, evidence index, and external blocker register.
- Fresh release archive, manifest, and independent archive verification.
- Completion percentage derived only from the final applicable matrix rows.

### 6. One-SHA promotion proof

- Run all web, mobile, API, database, agentend, security, accessibility,
  performance, package, and proof-hygiene gates on the exact final SHA.
- Push the closure branch and open a pull request.
- Do not merge, tag, or claim external provider success without the explicit
  required authority and evidence.

## Completion Rule

`PASS` means behavior and evidence both pass on the exact commit. A test name,
source file, old screenshot, or historical green run is not sufficient alone.
The final verdict remains `NUR_FINAL_HOLD` while any internal requirement,
external dependency, independent review, or founder release decision remains
open.
