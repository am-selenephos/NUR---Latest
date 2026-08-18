# NUR Independent Review Packet

## Review identity

| Field | Frozen value |
|---|---|
| Repository | `am-selenephos/NUR---Latest` |
| Completion branch | `completion/nur-fullstack-agentend-20260818` |
| Canonical base | `6b04918611c6edff9b20b76f0c7df2d950bf4d4d` |
| Frozen implementation/release-candidate SHA | `d012c5429bd035deb8a89b7fe19deb49c111356c` |
| Canonical main mutation | None permitted or performed |
| Current verdict | `NUR_PARTIAL` |
| Release artifact | Verified HOLD package from candidate SHA `d012c5429bd035deb8a89b7fe19deb49c111356c`; 829 entries, 9,223,046 uncompressed bytes, archive SHA-256 `eec71366616ac4495c9e7a82f26a0d63b123460d0bad03ceff16e33c34bd04c3`; secret/V197/naming scans PASS |

> This document prepares an independent review. It is **not** an independent review or approval, and it does not convert any held gate into a pass.

## Review objective

The reviewer should determine whether candidate SHA `d012c5429bd035deb8a89b7fe19deb49c111356c` truthfully closes the Full-Stack + Agentend Addendum in dependency order, whether the semantic E3–E8 and F1–F5 implementations have behavioral rather than nominal coverage, and whether the remaining `NUR_PARTIAL` blockers are correctly classified.

The implementation and browser-proof changes are frozen at the candidate SHA above. Documentation-only evidence commits after that candidate must not be treated as product-code changes. The branch must not be merged, tagged, renamed, or used to alter canonical `main` while any applicable hold remains.

## Gate summary

| Gate | Frozen status | Evidence or reason |
|---|---|---|
| A1–A5 | PASS | Repository truth, candidate reconciliation, isolated worktree, donor inventory, and public-safety audit |
| B1–B6 | PASS | Contract matrix, retry/approval/capability fixes, drift gate, and full-stack gateway proof |
| C1 | EXTERNAL-BLOCKED | Live provider is disabled; provider success was not fabricated |
| C2–C5 | PASS | Workflow proposal, approval, broker, and verified-result evidence |
| D1–D6 | PASS | Packet composition, beliefs, goals, manifest, owner boundaries, and token budget |
| E1–E8 | PASS | Semantic Brain components and real offline held-out/shadow evaluation runner; live provider remains separate |
| F1–F4 | PASS | Semantic hydration, DAG limits, browser-safe event reducer, and direct WorkflowProposalV2 path |
| F5 | PASS-CANDIDATE | Backend plus dedicated Chromium browser proof covers preview-without-write, explicit owner save, canonical workflow/proposal, approval, exactly one durable Plan, reload persistence, and duplicate-save idempotency |
| G1–G6 | PASS | Reconciliation, belief change, WhyChanged, memory effect, hardness, and empirical evaluation gate |
| Phase H | PASS-CANDIDATE / PARTIAL mix | Community, Capsule, Map, Orbit, Notifications, Localization, Today, Talk, Plan, and Systems focused/full-interface proofs are candidate-green; Insights broad seeded review breadth and Research broad live/seeded breadth remain partial |
| I1–I5 | PASS | RLS, CSRF/origin, replay, injection, and Actions hardening |
| I6 | HOLD-DEPENDENCY | Main branch protection/rulesets require repository-admin authority and were intentionally not changed |
| I7 | PASS | CycloneDX SBOM: 133 JavaScript and 63 Python components |
| J1 | PASS-CANDIDATE | Explicit local `nur_b6`/Redis smoke returns `/readyz 200`; official Docker is unavailable in the sandbox |
| J2–J5 | PASS | Backup/restore, crash/recovery, and static release gate |
| J6 | HOLD-DEPENDENCY | Approved live provider credential and reachable model catalog unavailable |
| J7 | PASS-CANDIDATE | Chromium desktop 17 passed/1 skipped; Chromium mobile 10 passed |
| J8 | PARTIAL | Final WebKit HOLD route 1 passed after iframe/fixture/SSE/Omega repairs; responsive matrix remains 3 passed and 1 browser page-closure failure; Track-A/direct-host proofs green |
| J9 | PASS | Verified HOLD package and integrity scans |
| J10 | HOLD-DEPENDENCY | This packet is review preparation, not independent signoff |
| K1 | PASS-CANDIDATE | Draft PR #2 exists from the dedicated branch |
| K2 | HOLD-DEPENDENCY | Prior exact-head run [32109905634](https://github.com/am-selenephos/NUR---Latest/actions/runs/32109905634) failed on pre-d012 docs head; corrected candidate d012c54 still requires a fresh exact-head run |
| K3–K5 | HOLD-DEPENDENCY | No merge, main CI, or tag while applicable gates remain held |
| K6 | PASS-CANDIDATE | Rename/rollback runbook documented; rename intentionally unexecuted |

## Behavioral semantic evidence

The E3–E8 correction requirements are covered by `apps/api/app/tests/test_brain_semantic_addendum.py`. The final suite passes seven tests. The real evaluator in `apps/api/app/brain/evaluation.py` calls the bounded planner, simulator, critic, router, research adapter, specialist worker, and memory-learning safety boundary. It does not call a live provider, approve a workflow, write owner memory, or mutate production state. `EvaluationGate` requires exact corpus version, non-empty held-out and shadow splits, full thresholds, and no failures.

F1–F4 are covered by `apps/api/app/tests/test_f1_f4_semantics.py`, the capability regression suite, and the web reducer tests. The hydrator receives approved semantic families through the cognitive loop and packet builder. The DAG validator is wired into compilation. Browser events are reduced through an allowlisted vocabulary. The worker dispatcher constructs `WorkflowProposalV2` directly.

F5 is now candidate-green. `apps/web/e2e/f5-plan-from-conversation.spec.ts` proves a Talk conversation renders preview without a workflow proposal, explicit owner save emits the canonical proposal, approval is required and accepted, exactly one durable Plan is visible, reload preserves the same Plan, and duplicate save does not create another Plan. The backend runtime proof remains the complementary real-stack authority-boundary evidence.

## Runtime and browser evidence

J1 was reproduced as an environment mismatch. The readiness endpoint checks PostgreSQL `SELECT 1` and Redis `PING`; the boot-smoke defaults to the wrong local database and credentials. With the working values, `/readyz`, `/healthz`, and `/metrics` each returned 200 and SIGTERM completed with `rc=143`.

The Chromium desktop/mobile matrices are green at the recorded totals, and the focused final Chromium core-route/control/responsive/Universe-lens rerun is 13 passed and 3 skipped. The final WebKit HOLD route is now 1 passed after iframe-owned selectors, authenticated snapshot/CSRF fixtures, current Talk SSE, Omega route fixtures, and current copy assertions were repaired. The responsive WebKit matrix remains 3 passed and 1 browser page-closure failure. These results are recorded in `docs/completion/MANUS_J7_J8_BROWSER_MATRIX.md`; no assertion was lowered to suppress them.

## Required verification commands

Run these commands from candidate SHA `d012c5429bd035deb8a89b7fe19deb49c111356c`, using the repository’s configured services where required:

```bash
cd apps/api
python3 -m pytest -q \
  app/tests/test_brain_semantic_addendum.py \
  app/tests/test_f1_f4_semantics.py \
  app/tests/test_capability_loop_integration.py \
  app/tests/test_capability_runtime_e2e.py

cd apps/web
pnpm run typecheck
pnpm exec vitest run
pnpm run build
```

Expected local results from the frozen implementation are **20 backend tests passed**, **115 web unit tests passed across 23 files**, successful typecheck, and successful production build. Vite emits existing warnings about native config compatibility and chunk size; those warnings are not type or build failures.

The browser commands are:

```bash
cd apps/web
CI=1 pnpm exec playwright test --project=chromium-desktop --workers=1
CI=1 pnpm exec playwright test --project=chromium-mobile --workers=1
CI=1 pnpm exec playwright test e2e/final-webkit-mobile.spec.ts --project=webkit-mobile --workers=1
CI=1 pnpm exec playwright test e2e/v197-responsive-accessibility.spec.ts --project=webkit-mobile --workers=1
```

The reviewer should compare actual results with the J7/J8 note rather than assuming the matrix is fully green.

## Architecture-sensitive diff checklist

The following changes deserve manual review because they affect trust boundaries or cross-layer contracts:

| Area | Files | Review question |
|---|---|---|
| Brain semantics | `apps/api/app/brain/planner.py`, `critic.py`, `research.py`, `specialists.py`, `evaluation.py` | Are candidates bounded, uncertainty preserved, external text treated as evidence rather than authority, and promotion tied to empirical held-out/shadow output? |
| Mind hydration | `apps/api/app/mind/context.py`, `apps/api/app/mind/capabilities/hydrator.py`, `apps/api/app/mind/cognitive_loop.py` | Are approved semantic families owner-scoped and passed consistently into both hydration and the CognitiveTaskPacket? |
| Agency limits | `apps/api/app/agentic/limits.py`, `apps/api/app/agentic/compiler.py` | Are width, depth, fan-out, cost, and deadline limits enforced before execution without bypass paths? |
| Proposal contract | `apps/api/app/mind/capabilities/dispatcher.py`, `apps/api/app/brain/schemas.py` | Is WorkflowProposalV2 constructed directly and does approval remain the only durable-write authority boundary? |
| Browser event safety | `apps/web/src/bridge/v197CapabilityReducer.ts` | Does browser state remain allowlisted and free of raw internal payloads? |
| Route ownership | `apps/web/src/bridge/v197Bridge.ts`, `v197Events.ts`, `v197Hydration.ts`, `v197Adjuncts.ts`, `apps/web/vite.config.ts` | Do supported Community/Consultation/Notifications/Localization routes survive host normalization, deep links, reload, and owner scoping? |
| Browser proofs | `apps/web/e2e/track-a-mobile-webkit.spec.ts`, `v197-core-routes-forensic.spec.ts`, `v197-adjuncts.spec.ts`, `full-interface.spec.ts` | Are current DOM contracts asserted without stale selectors, hidden-node acceptance, or weakened geometry checks? |

## External blockers and next actions

The live provider gate requires an approved reachable model catalog and credential; the local provider-disabled response is the truthful result. I6 requires repository-administrator configuration of branch protection/rulesets. K2 remains held pending a fresh exact-head run for candidate SHA `d012c5429bd035deb8a89b7fe19deb49c111356c`; prior run [32109905634](https://github.com/am-selenephos/NUR---Latest/actions/runs/32109905634) failed on the pre-d012 documentation head because the Systems geometry assertion rejected the canonical global Community navigation entry. Docker cold boot requires release infrastructure with Docker. J8 retains one responsive WebKit page-closure failure and needs either a supported-browser infrastructure exception or a browser-runtime fix. F5 is closed at the candidate browser-proof boundary. J10 requires a reviewer who is independent of this implementation pass.

The completion branch was pushed through prior documentation head `10dce5f9485e56af820f1c0010d20d3d85be5c74` and PR #2 was updated. The corrected candidate `d012c5429bd035deb8a89b7fe19deb49c111356c` and its final evidence commit now require publication, followed by a fresh exact-head CI run; no canonical-main operation is permitted.

## Review decision record

The reviewer should append a signed or otherwise attributable decision outside this document. Until then, the only valid branch verdict is:

> **NUR_PARTIAL — verified HOLD artifact; no canonical main changes.**
