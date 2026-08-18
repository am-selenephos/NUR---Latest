# NUR Independent Review Packet

## Review identity

| Field | Frozen value |
|---|---|
| Repository | `am-selenephos/NUR---Latest` |
| Completion branch | `completion/nur-fullstack-agentend-20260818` |
| Canonical base | `6b04918611c6edff9b20b76f0c7df2d950bf4d4d` |
| Frozen implementation SHA | `a1608eeed715b9716729a184c239565f3a7d0ded` |
| Frozen release-candidate SHA | `13fd8475958cb42d3b4876c3507a48d09f0e5108` |
| Canonical main mutation | None permitted or performed |
| Current verdict | `NUR_PARTIAL` |
| Release artifact | Verified HOLD package from the release candidate; 827 entries, 9,194,920 uncompressed bytes, archive SHA-256 `90ca968acdf9bf6c85c781c5fb4efd8cbca4553d203e7edf4fc0bbfc2038bc5d` |

> This document prepares an independent review. It is **not** an independent review or approval, and it does not convert any held gate into a pass.

## Review objective

The reviewer should determine whether the completion branch truthfully closes the Full-Stack + Agentend Addendum in dependency order, whether the semantic E3–E8 and F1–F4 implementations have behavioral rather than nominal coverage, and whether the remaining `NUR_PARTIAL` blockers are correctly classified. The reviewer should verify both the frozen implementation SHA and the documentation-complete release-candidate SHA before relying on any result in this packet.

The implementation was completed before the SHA was frozen. Documentation-only changes made after the freeze must not be treated as product-code changes. The branch must not be merged, tagged, renamed, or used to alter canonical `main` while any applicable hold remains.

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
| F5 | PARTIAL | Dedicated browser conversation-to-durable-Plan reload/idempotency proof is not yet present |
| G1–G6 | PASS | Reconciliation, belief change, WhyChanged, memory effect, hardness, and empirical evaluation gate |
| Phase H | PARTIAL / PASS-CANDIDATE mix | Community, Capsule, Map, Orbit, Notifications, and Localization focused proofs green; Insights, Research, and complete route breadth remain incomplete |
| I1–I5 | PASS | RLS, CSRF/origin, replay, injection, and Actions hardening |
| I6 | HOLD-DEPENDENCY | Main branch protection/rulesets require repository-admin authority and were intentionally not changed |
| I7 | PASS | CycloneDX SBOM: 133 JavaScript and 63 Python components |
| J1 | PASS-CANDIDATE | Explicit local `nur_b6`/Redis smoke returns `/readyz 200`; official Docker is unavailable in the sandbox |
| J2–J5 | PASS | Backup/restore, crash/recovery, and static release gate |
| J6 | HOLD-DEPENDENCY | Approved live provider credential and reachable model catalog unavailable |
| J7 | PASS-CANDIDATE | Chromium desktop 17 passed/1 skipped; Chromium mobile 10 passed |
| J8 | PARTIAL | WebKit mobile 7 passed, 2 flaky retry-only, 2 failed; Track-A/direct-host isolated proofs green |
| J9 | PASS | Verified HOLD package and integrity scans |
| J10 | HOLD-DEPENDENCY | This packet is review preparation, not independent signoff |
| K1 | PASS-CANDIDATE | Draft PR #2 exists from the dedicated branch |
| K2 | HOLD-DEPENDENCY | Definitive remote exact-head CI requires authenticated push and completion |
| K3–K5 | HOLD-DEPENDENCY | No merge, main CI, or tag while applicable gates remain held |
| K6 | PASS-CANDIDATE | Rename/rollback runbook documented; rename intentionally unexecuted |

## Behavioral semantic evidence

The E3–E8 correction requirements are covered by `apps/api/app/tests/test_brain_semantic_addendum.py`. The final suite passes seven tests. The real evaluator in `apps/api/app/brain/evaluation.py` calls the bounded planner, simulator, critic, router, research adapter, specialist worker, and memory-learning safety boundary. It does not call a live provider, approve a workflow, write owner memory, or mutate production state. `EvaluationGate` requires exact corpus version, non-empty held-out and shadow splits, full thresholds, and no failures.

F1–F4 are covered by `apps/api/app/tests/test_f1_f4_semantics.py`, the capability regression suite, and the web reducer tests. The hydrator receives approved semantic families through the cognitive loop and packet builder. The DAG validator is wired into compilation. Browser events are reduced through an allowlisted vocabulary. The worker dispatcher constructs `WorkflowProposalV2` directly.

F5 is intentionally not claimed. The missing proof must use a real browser conversation, a preview that writes nothing, explicit owner save, canonical workflow/proposal, approval, exactly one durable Plan, reload persistence, and duplicate-save/idempotency behavior.

## Runtime and browser evidence

J1 was reproduced as an environment mismatch. The readiness endpoint checks PostgreSQL `SELECT 1` and Redis `PING`; the boot-smoke defaults to the wrong local database and credentials. With the working values, `/readyz`, `/healthz`, and `/metrics` each returned 200 and SIGTERM completed with `rc=143`.

The Chromium desktop and mobile matrices are green at the totals recorded above. WebKit mobile has a truthful partial result. The final WebKit HOLD test still expects top-level `#page-systems` after `/systems`, while the current route is iframe-owned. The responsive retry includes a WebKit page crash. These results are recorded in `docs/completion/MANUS_J7_J8_BROWSER_MATRIX.md`; no assertion was lowered to suppress them.

## Required verification commands

Run these commands from the frozen SHA, using the repository’s configured services where required:

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
CI=1 pnpm exec playwright test --project=webkit-mobile --workers=1
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

The live provider gate requires an approved reachable model catalog and credential; the local provider-disabled response is the truthful result. I6 requires repository-administrator configuration of branch protection/rulesets. K2 requires an authenticated maintainer to push the frozen branch and wait for definitive exact-head CI. Docker cold boot requires release infrastructure with Docker. J8 requires either correction of the stale WebKit route-boundary proof and investigation of the WebKit crash or an explicitly approved supported-browser infrastructure exception. F5 requires the dedicated browser plan-from-conversation proof. J10 requires a reviewer who is independent of this implementation pass.

The last sandbox push attempt failed because the configured GitHub CLI token was invalid. Therefore, this packet’s exact-SHA evidence is locally frozen at release-candidate SHA `13fd8475958cb42d3b4876c3507a48d09f0e5108`, but final remote publication and CI state must be completed by an authenticated maintainer.

## Review decision record

The reviewer should append a signed or otherwise attributable decision outside this document. Until then, the only valid branch verdict is:

> **NUR_PARTIAL — verified HOLD artifact; no canonical main changes.**
