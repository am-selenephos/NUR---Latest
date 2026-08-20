# NUR Final Requirement Matrix — 2026-08-20

**Matrix source SHA:** `caf58863e93b47b4c148c11d86efdd1245354ef1`  
**Status:** Initial reconciliation before exact-main reruns; `PASS-CANDIDATE` means prior evidence is not yet re-stamped to this exact SHA.

## Explicit denominator summary

| Metric | Numerator / denominator | Result |
| --- | ---: | ---: |
| Applicable rows | 129 | — |
| Implementation completion | 0 / 106 | 0.00% |
| Evidence completion | 0 / 7 | 0.00% |
| Release completion | 0 / 16 | 0.00% |

## Status counts

| Status | Count |
| --- | ---: |
| PASS | 0 |
| PASS-CANDIDATE | 63 |
| PARTIAL | 29 |
| FAIL | 0 |
| EXTERNAL_BLOCKED | 4 |
| ADMIN_BLOCKED | 0 |
| FOUNDER_DECISION | 0 |
| NOT_PROVEN | 33 |
| NOT_APPLICABLE | 0 |
| SUPERSEDED | 0 |

## Remaining counts

- Remaining internally solvable rows: **62**
- Remaining external rows: **4**
- Remaining founder-decision rows: **0**
- Superseded/not-applicable rows: **0**

## Matrix

The complete row-level matrix is the adjacent CSV. The rows below show the current exact-main reconciliation fields for every row; evidence is intentionally conservative until the exact-main gate rerun is complete.

| ID | Phase | Task | Status | Exact SHA/evidence | Blocker | Next action |
| --- | --- | --- | --- | --- | --- | --- |
| A1 | A | Environment and Git truth | PASS-CANDIDATE | `d012c5429bd035deb8a89b7fe19deb49c111356c` | NONE | None |
| A2 | A | Resolve candidate repo's own ahead branch | PASS-CANDIDATE | `d012c5429bd035deb8a89b7fe19deb49c111356c` | NONE | Insights route ownership and broader contract reconciliation continue in Phase B |
| A3 | A | Create isolated canonical integration worktree | PASS-CANDIDATE | `d012c5429bd035deb8a89b7fe19deb49c111356c` | NONE | None |
| A4 | A | Donor inventory | NOT_PROVEN | `PASS` | ef86827abd5c2fa701d24ab3df9cb6c1edb9131c | ef86827abd5c2fa701d24ab3df9cb6c1edb9131c |
| A5 | A | Public-safety audit | NOT_PROVEN | `or second Three.js renderer in candidate diff` | secret-scan.sh; direct-provider/runtime grep | secret-scan.sh; direct-provider/runtime grep |
| B1 | B | Generate current route/client contract matrix | PASS-CANDIDATE | `d012c5429bd035deb8a89b7fe19deb49c111356c` | NONE | None |
| B2 | B | Fix Agent retry mismatch | PASS-CANDIDATE | `d012c5429bd035deb8a89b7fe19deb49c111356c` | NONE | None |
| B3 | B | Expose Approval EDIT | PASS-CANDIDATE | `d012c5429bd035deb8a89b7fe19deb49c111356c` | NONE | Full live HTTP/worker EDIT proof remains a later release gate |
| B4 | B | Add capability_id and memory_mode to streaming Talk client | PASS-CANDIDATE | `d012c5429bd035deb8a89b7fe19deb49c111356c` | NONE | Full-stack SSE/reload proof remains B6/C1 |
| B5 | B | OpenAPI drift gate | PASS-CANDIDATE | `d012c5429bd035deb8a89b7fe19deb49c111356c` | NONE | None |
| B6 | B | Full-stack gateway vertical test | PASS-CANDIDATE | `d012c5429bd035deb8a89b7fe19deb49c111356c` | NONE | None |
| C1 | C | Talk answer-only E2E | EXTERNAL_BLOCKED | `d012c5429bd035deb8a89b7fe19deb49c111356c` | EXTERNAL | Live provider catalog returned HTTP 404 and no application model is configured; no fake success claimed |
| C2 | C | Talk workflow proposal E2E | NOT_PROVEN | `PASS` | not yet reconciled |  |
| C3 | C | Approval E2E | PASS-CANDIDATE | `None` | NONE | PASS |
| C4 | C | Beat/worker E2E | PASS-CANDIDATE | `d012c5429bd035deb8a89b7fe19deb49c111356c` | NONE | None |
| C5 | C | Verified-result UI E2E | NOT_PROVEN | `and success criterion evidence` | real Chromium; live FastAPI/PostgreSQL/RLS/Redis/Celery worker+beat; browser test passed | real Chromium; live FastAPI/PostgreSQL/RLS/Redis/Celery worker+beat; browser test passed |
| D1 | D | Audit CognitiveTaskPacket | PASS-CANDIDATE | `d012c5429bd035deb8a89b7fe19deb49c111356c` | NONE | None |
| D2 | D | User/Self/World model composition | NOT_PROVEN | `PASS` | not yet reconciled |  |
| D3 | D | Belief and counterevidence composition | NOT_PROVEN | `apps/api/app/mind/beliefs.py; apps/api/app/tests/test_beliefs_attention_phase3.py; apps/api/app/tests/test_omega.py` | and staleness behavior is covered | and staleness behavior is covered |
| D4 | D | Goals and intention arbitration | PASS-CANDIDATE | `d012c5429bd035deb8a89b7fe19deb49c111356c` | NONE | None |
| D5 | D | Context manifest | PASS-CANDIDATE | `d012c5429bd035deb8a89b7fe19deb49c111356c` | NONE | None |
| D6 | D | Cross-owner and token-budget tests | NOT_PROVEN | `PASS` | not yet reconciled |  |
| E1 | E | Version CognitiveTaskPacketV2/CognitiveResultV2 | PASS-CANDIDATE | `d012c5429bd035deb8a89b7fe19deb49c111356c` | NONE | None |
| E2 | E | Harden Brain router | NOT_PROVEN | `apps/api/app/brain/router.py; apps/api/app/tests/test_addendum_dg_contracts.py` | and budget downgrade | and budget downgrade |
| E3 | E | Typed Planner | PASS-CANDIDATE | `d012c5429bd035deb8a89b7fe19deb49c111356c` | NONE | None |
| E4 | E | Bounded Simulator | PASS-CANDIDATE | `d012c5429bd035deb8a89b7fe19deb49c111356c` | NONE | None |
| E5 | E | Separate deterministic validator from independent critic | PASS-CANDIDATE | `d012c5429bd035deb8a89b7fe19deb49c111356c` | NONE | None |
| E6 | E | Research Brain | PASS-CANDIDATE | `d012c5429bd035deb8a89b7fe19deb49c111356c` | NONE | External retrieval/connectors remain outside this local proof |
| E7 | E | Specialist workers | PASS-CANDIDATE | `d012c5429bd035deb8a89b7fe19deb49c111356c` | NONE | None |
| E8 | E | Evaluation corpus | NOT_PROVEN | `and memory-learning safety components across development` | specialist | specialist |
| F1 | F | Hydration tier parity | NOT_PROVEN | `3 F1/F2/F4 semantic tests plus capability regression suite passed` | apps/api/app/mind/capabilities/hydrator.py; apps/api/app/mind/context.py; apps/api/app/mind/cognitive_loop.py; apps/api/app/tests/test_f1_f4_semantics.py | apps/api/app/mind/capabilities/hydrator.py; apps/api/app/mind/context.py; apps/api/app/mind/cognitive_loop.py; apps/api/app/tests/test_f1_f4_semantics.py |
| F2 | F | Worker DAG limits | NOT_PROVEN | `3 F1/F2/F4 semantic tests passed` | apps/api/app/agentic/limits.py; apps/api/app/agentic/compiler.py; apps/api/app/tests/test_f1_f4_semantics.py | apps/api/app/agentic/limits.py; apps/api/app/agentic/compiler.py; apps/api/app/tests/test_f1_f4_semantics.py |
| F3 | F | Safe event parity | PASS-CANDIDATE | `d012c5429bd035deb8a89b7fe19deb49c111356c` | NONE | None |
| F4 | F | WorkflowProposalV2 | PASS-CANDIDATE | `d012c5429bd035deb8a89b7fe19deb49c111356c` | NONE | None |
| F5 | F | Plan-from-conversation production proof | NOT_PROVEN | `and duplicate-save idempotency` | reload persistence | reload persistence |
| H-AGENTS | H | Phase-H owner route: Agents; owner API, durable state, RLS, V197 render, mutation, reload, empty/error state, mobile, accessibility, E2E | PASS-CANDIDATE | `d012c5429bd035deb8a89b7fe19deb49c111356c` | NONE | Independent empty/error/mobile route matrix remains |
| H-BILLING | H | Phase-H owner route: Billing; owner API, durable state, RLS, V197 render, mutation, reload, empty/error state, mobile, accessibility, E2E | PASS-CANDIDATE | `d012c5429bd035deb8a89b7fe19deb49c111356c` | NONE | Live billing provider proof remains external |
| H-CAPSULES | H | Phase-H owner route: Capsules; owner API, durable state, RLS, V197 render, mutation, reload, empty/error state, mobile, accessibility, E2E | NOT_PROVEN | `Focused and real two-account Capsule proofs green` | apps/web/e2e/owner-product-surfaces.spec.ts; apps/web/e2e/capsule.spec.ts | apps/web/e2e/owner-product-surfaces.spec.ts; apps/web/e2e/capsule.spec.ts |
| H-COMMUNITY | H | Phase-H owner route: Community; owner API, durable state, RLS, V197 render, mutation, reload, empty/error state, mobile, accessibility, E2E | NOT_PROVEN | `and Council flow pass with the documented owner/recipient fixture` | Glow evidence | Glow evidence |
| H-INSIGHTS | H | Phase-H owner route: Insights; owner API, durable state, RLS, V197 render, mutation, reload, empty/error state, mobile, accessibility, E2E | PARTIAL | `d012c5429bd035deb8a89b7fe19deb49c111356c` | Stabilize fresh route fixture and run dedicated proof | Stabilize fresh route fixture and run dedicated proof |
| H-JOURNAL | H | Phase-H owner route: Journal; owner API, durable state, RLS, V197 render, mutation, reload, empty/error state, mobile, accessibility, E2E | PASS-CANDIDATE | `d012c5429bd035deb8a89b7fe19deb49c111356c` | NONE | Independent full route matrix still pending |
| H-LOCALIZATION | H | Phase-H owner route: Localization; owner API, durable state, RLS, V197 render, mutation, reload, empty/error state, mobile, accessibility, E2E | NOT_PROVEN | `a1608ee` | Localization route and reload persistence proof green | Localization route and reload persistence proof green |
| H-MAP | H | Phase-H owner route: Map; owner API, durable state, RLS, V197 render, mutation, reload, empty/error state, mobile, accessibility, E2E | NOT_PROVEN | `reload` | confirmed-edge explanation | confirmed-edge explanation |
| H-MEMORY | H | Phase-H owner route: Memory; owner API, durable state, RLS, V197 render, mutation, reload, empty/error state, mobile, accessibility, E2E | PASS-CANDIDATE | `d012c5429bd035deb8a89b7fe19deb49c111356c` | NONE | Fresh independent route matrix remains |
| H-NOTIFICATIONS | H | Phase-H owner route: Notifications; owner API, durable state, RLS, V197 render, mutation, reload, empty/error state, mobile, accessibility, E2E | NOT_PROVEN | `apps/web/src/bridge/v197Adjuncts.ts; apps/web/e2e/v197-adjuncts.spec.ts` | and accessible controls | and accessible controls |
| H-ORBIT | H | Phase-H owner route: Orbit; owner API, durable state, RLS, V197 render, mutation, reload, empty/error state, mobile, accessibility, E2E | NOT_PROVEN | `accessibility` | mobile | mobile |
| H-PLAN | H | Phase-H owner route: Plan; owner API, durable state, RLS, V197 render, mutation, reload, empty/error state, mobile, accessibility, E2E | PASS-CANDIDATE | `d012c5429bd035deb8a89b7fe19deb49c111356c` | NONE | Independent complete route matrix remains |
| H-PROJECTS | H | Phase-H owner route: Projects; owner API, durable state, RLS, V197 render, mutation, reload, empty/error state, mobile, accessibility, E2E | NOT_PROVEN | `PASS-CANDIDATE` | not yet reconciled |  |
| H-RESEARCH | H | Phase-H owner route: Research; owner API, durable state, RLS, V197 render, mutation, reload, empty/error state, mobile, accessibility, E2E | PARTIAL | `Stabilize fresh research fixtures` | PARTIAL | PARTIAL |
| H-SYSTEMS | H | Phase-H owner route: Systems; owner API, durable state, RLS, V197 render, mutation, reload, empty/error state, mobile, accessibility, E2E | PASS-CANDIDATE | `d012c5429bd035deb8a89b7fe19deb49c111356c` | NONE | Independent complete route matrix remains |
| H-TALK | H | Phase-H owner route: Talk; owner API, durable state, RLS, V197 render, mutation, reload, empty/error state, mobile, accessibility, E2E | NOT_PROVEN | `and semantic stream UI pass; live provider remains external-blocked` | focused Talk browser tests passed; C1 provider-disabled path passed | focused Talk browser tests passed; C1 provider-disabled path passed |
| H-TIMELINE | H | Phase-H owner route: Timeline; owner API, durable state, RLS, V197 render, mutation, reload, empty/error state, mobile, accessibility, E2E | PASS-CANDIDATE | `d012c5429bd035deb8a89b7fe19deb49c111356c` | NONE | Independent complete route matrix remains |
| H-TODAY | H | Phase-H owner route: Today; owner API, durable state, RLS, V197 render, mutation, reload, empty/error state, mobile, accessibility, E2E | PASS-CANDIDATE | `d012c5429bd035deb8a89b7fe19deb49c111356c` | NONE | Independent complete route matrix remains |
| I1 | I | RLS matrix | PASS-CANDIDATE | `d012c5429bd035deb8a89b7fe19deb49c111356c` | NONE | None |
| I2 | I | CSRF and origin matrix | PASS-CANDIDATE | `d012c5429bd035deb8a89b7fe19deb49c111356c` | NONE | None |
| I3 | I | Agent replay attacks | PASS-CANDIDATE | `d012c5429bd035deb8a89b7fe19deb49c111356c` | NONE | None |
| I4 | I | Prompt and tool injection corpus | PASS-CANDIDATE | `d012c5429bd035deb8a89b7fe19deb49c111356c` | NONE | No live provider claim; corpus is deterministic local boundary evidence |
| I5 | I | GitHub Actions hardening | PASS-CANDIDATE | `d012c5429bd035deb8a89b7fe19deb49c111356c` | NONE | None |
| I6 | I | Main branch ruleset | NOT_PROVEN | `d012c5429bd035deb8a89b7fe19deb49c111356c` | Applying repository settings would change canonical configuration and requires repository-administrator action outside the completion worktree | Applying repository settings would change canonical configuration and requires repository-administrator action outside the completion worktree |
| I7 | I | Dependency and SBOM | PASS-CANDIDATE | `d012c5429bd035deb8a89b7fe19deb49c111356c` | NONE | None |
| J1 | J | Cold boot | PASS-CANDIDATE | `d012c5429bd035deb8a89b7fe19deb49c111356c` | NONE | Docker is not installed in this sandbox; rerun official Docker cold boot in release infrastructure |
| J10 | J | Independent final review | NOT_PROVEN | `Requires an independent reviewer and final route/release matrix` | HOLD-DEPENDENCY | HOLD-DEPENDENCY |
| J2 | J | Backup | PASS-CANDIDATE | `d012c5429bd035deb8a89b7fe19deb49c111356c` | NONE | Local isolated proof only; not production backup-service availability |
| J3 | J | Restore drill | PASS-CANDIDATE | `d012c5429bd035deb8a89b7fe19deb49c111356c` | NONE | Local isolated proof only |
| J4 | J | Crash and recovery drill | PASS-CANDIDATE | `d012c5429bd035deb8a89b7fe19deb49c111356c` | NONE | None |
| J5 | J | Static release gate | PASS-CANDIDATE | `d012c5429bd035deb8a89b7fe19deb49c111356c` | NONE | No live provider claim |
| J6 | J | Live provider gate | NOT_PROVEN | `d012c5429bd035deb8a89b7fe19deb49c111356c` | Approved live provider credential and reachable model catalog are unavailable | Approved live provider credential and reachable model catalog are unavailable |
| J7 | J | Real-stack browser matrix | NOT_PROVEN | `Track-A` | adaptive performance | adaptive performance |
| J8 | J | Cross-browser, accessibility, and performance | NOT_PROVEN | `PARTIAL` | d012c5429bd035deb8a89b7fe19deb49c111356c | d012c5429bd035deb8a89b7fe19deb49c111356c |
| J9 | J | Fresh-extract artifact | PASS-CANDIDATE | `d012c5429bd035deb8a89b7fe19deb49c111356c` | NONE | Artifact is intentionally HOLD, not FULL_PASS |
| K1 | K | Final integration PR | PASS-CANDIDATE | `then update PR #2` | NONE | Publish corrected candidate d012c5429bd035deb8a89b7fe19deb49c111356c and final evidence |
| K2 | K | Exact-head CI | NOT_PROVEN | `HOLD-DEPENDENCY` | d012c5429bd035deb8a89b7fe19deb49c111356c | d012c5429bd035deb8a89b7fe19deb49c111356c |
| K3 | K | Merge | NOT_PROVEN | `d012c5429bd035deb8a89b7fe19deb49c111356c` | Do not merge until every applicable release gate is green on one exact SHA | Do not merge until every applicable release gate is green on one exact SHA |
| K4 | K | Main CI | NOT_PROVEN | `d012c5429bd035deb8a89b7fe19deb49c111356c` | Requires a permitted exact-head merge and protected-main CI | Requires a permitted exact-head merge and protected-main CI |
| K5 | K | Tag | NOT_PROVEN | `d012c5429bd035deb8a89b7fe19deb49c111356c` | Tag only after full-pass approval and main CI | Tag only after full-pass approval and main CI |
| K6 | K | Repository rename runbook | PASS-CANDIDATE | `d012c5429bd035deb8a89b7fe19deb49c111356c` | NONE | Administrative rename requires post-promotion owner action |
| LEGACY-C001 | PRODUCT | source integrity | PARTIAL | `` | control matrix currently stamped from an older SHA | Regenerate and validate matrix on final tree without a self-invalidating SHA stamp |
| LEGACY-C002 | PRODUCT | cold boot | PARTIAL | `` | not yet repeated from a fresh package at final SHA | Run fresh-extract package smoke |
| LEGACY-C003 | PRODUCT | authentication | PASS-CANDIDATE | `` |  | Keep in final gate |
| LEGACY-C004 | PRODUCT | password recovery | EXTERNAL_BLOCKED | `` | EXTERNAL | Keep internal PASS and require one verified sender/provider action |
| LEGACY-C005 | PRODUCT | sessions and CSRF | PASS-CANDIDATE | `` |  | Keep in final gate |
| LEGACY-C006 | PRODUCT | owner isolation and RLS | PASS-CANDIDATE | `` |  | Run again after every new migration |
| LEGACY-C007 | PRODUCT | Talk and OpenAI | EXTERNAL_BLOCKED | `` | EXTERNAL | Run only with existing valid local credential; never copy or rotate |
| LEGACY-C008 | PRODUCT | streaming cancellation persistence | PARTIAL | `` | full real-stack browser test and cancellation race not green | Fix current failures and add cancellation-race proof |
| LEGACY-C009 | PRODUCT | Today | PASS-CANDIDATE | `` |  | Keep in final gate |
| LEGACY-C010 | PRODUCT | Journal | PASS-CANDIDATE | `` |  | Keep in final gate |
| LEGACY-C011 | PRODUCT | Plan | PARTIAL | `` | edit direction is visible honest-disabled | Implement the owner edit flow or remove the obsolete control |
| LEGACY-C012 | PRODUCT | Systems | PASS-CANDIDATE | `` |  | Remove stale seven-System tests without restoring retired product state |
| LEGACY-C013 | PRODUCT | Map | PASS-CANDIDATE | `` |  | Refresh stale fixture names |
| LEGACY-C014 | PRODUCT | Orbits | PASS-CANDIDATE | `` |  | Keep in final gate |
| LEGACY-C015 | PRODUCT | Timeline | PASS-CANDIDATE | `` |  | Keep in final gate |
| LEGACY-C016 | PRODUCT | Insights | PASS-CANDIDATE | `` |  | Keep in final gate |
| LEGACY-C017 | PRODUCT | Research | PARTIAL | `` | live retrieval and complete job UI absent | Finish provider-neutral UI and retain external fetch blocker |
| LEGACY-C018 | PRODUCT | Web Signals | PARTIAL | `` | alert management and live retrieval UI incomplete | Finish local owner workflows then keep provider fail-closed |
| LEGACY-C019 | PRODUCT | Community | PARTIAL | `` | future tabs and realtime gateway incomplete | Port bounded current-compatible realtime and finish or hide deferred routes |
| LEGACY-C020 | PRODUCT | Rooms | PASS-CANDIDATE | `` |  | Keep in final gate |
| LEGACY-C021 | PRODUCT | Group NUR | PASS-CANDIDATE | `` |  | Keep in final gate |
| LEGACY-C022 | PRODUCT | Consultations | PASS-CANDIDATE | `` |  | Keep in final gate |
| LEGACY-C023 | PRODUCT | Projects | PARTIAL | `` | settings insights and share tabs are not complete | Finish or honestly remove each placeholder |
| LEGACY-C024 | PRODUCT | tasks | PASS-CANDIDATE | `` |  | Keep in final gate |
| LEGACY-C025 | PRODUCT | files | PASS-CANDIDATE | `` |  | Keep in final gate |
| LEGACY-C026 | PRODUCT | agent runs | PARTIAL | `` | capability breadth and full browser recovery proof limited | Finish bounded registry and evidence package UI without autonomy claims |
| LEGACY-C027 | PRODUCT | Context Capsules | PARTIAL | `` | recipient lifecycle exists but owner creation flow is missing | Build canonical owner workflow and two-account denial proof |
| LEGACY-C028 | PRODUCT | Personal Memory | PARTIAL | `` | no reachable canonical V197 surface | Add Memory adjunct route controls bridge and E2E |
| LEGACY-C029 | PRODUCT | Teach NUR | PARTIAL | `` | no reachable canonical V197 surface | Add Teach NUR adjunct route controls bridge and E2E |
| LEGACY-C030 | PRODUCT | Glow | PARTIAL | `` | abuse experiment and operational proof incomplete | Add bounded abuse controls and current operational tests |
| LEGACY-C031 | PRODUCT | Notifications | PARTIAL | `` | external adapters retry dead-letter and bounce handling incomplete | Complete adapter queue contracts and keep provider proof external |
| LEGACY-C032 | PRODUCT | translations and RTL | PARTIAL | `` | human review and extraction completeness unproven | Add extraction diagnostics and keep draft locales labeled |
| LEGACY-C033 | PRODUCT | Billing and entitlements | PARTIAL | `` | no V197 billing surface and no provider test-mode proof | Build provider-neutral V197 UI then run configured test provider |
| LEGACY-C034 | PRODUCT | Omega | PASS-CANDIDATE | `` |  | Run enabled Omega tests in final browser matrix |
| LEGACY-C035 | PRODUCT | Neural Simulation and TRIBE | NOT_PROVEN | `` | no current product implementation and gated licence/access | Implement provider-neutral disabled contract and surface; never ship weights |
| LEGACY-C036 | PRODUCT | backup and restore | PARTIAL | `` | final exact-SHA realistic drill not executed | Run isolated final drill and record measurements |
| LEGACY-C037 | PRODUCT | queue recovery | PARTIAL | `` | scheduled production operation unproven | Add scheduler invocation and runtime proof |
| LEGACY-C038 | PRODUCT | storage hygiene | PARTIAL | `` | scheduled sweep evidence absent | Run final isolated reconciliation and retention proof |
| LEGACY-C039 | PRODUCT | rate limits and quotas | PARTIAL | `` | coverage is not comprehensive across all costly mutations | Inventory routes and add missing limit tests |
| LEGACY-C040 | PRODUCT | security headers | PARTIAL | `` | HSTS and web-edge headers unproven | Add production-edge header gate |
| LEGACY-C041 | PRODUCT | secret handling | EXTERNAL_BLOCKED | `` | EXTERNAL | Founder verifies rotation; never print keys |
| LEGACY-C042 | PRODUCT | accessibility | PARTIAL | `` | full corpus stale and no complete axe or screen-reader run | Fix corpus then run desktop mobile RTL reduced-motion and manual AT audit |
| LEGACY-C043 | PRODUCT | mobile | PARTIAL | `` | full WebKit and native signing push secure-storage proof absent | Run browser matrix and classify external native credentials |
| LEGACY-C044 | PRODUCT | performance | PARTIAL | `` | stale assertions and final ten-minute CDP soak absent | Update current contracts then run measured final soak |
| LEGACY-C045 | PRODUCT | packaging | PARTIAL | `` | SBOM and complete verifier absent | Implement verifier exclusions SBOM and fresh boot |
| LEGACY-C046 | PRODUCT | CI | PARTIAL | `` | readiness currently runs only two mocked Chromium specs | Expand after full local corpus is current and deterministic |
| LEGACY-C047 | PRODUCT | documentation | PARTIAL | `` | multiple historical docs remain stale or conflicting | Supersede stale claims and publish final six artifacts |
| G00 | G00 | Evidence truth | Run current exact-main evidence reconciliation | `CURRENT_REQUIREMENT` |  |  |
| G01 | G01 | Static/security/dependency | Run exact-main gate and classify skips | `CURRENT_REQUIREMENT` |  |  |
| G02 | G02 | Auth/session/privacy/RLS | Capture exact-main receipt | `ALREADY_PROVEN` |  |  |
| G03 | G03 | Canonical V197/control contracts | Run current exact-main integrity and browser gates | `ALREADY_PROVEN` |  |  |
| G04 | G04 | Performance/accessibility | Run corrected matrix and measured soak | `CURRENT_REQUIREMENT` |  |  |
| G05 | G05 | Live AI/provider | Rerun with secure local credential if available | `EXTERNAL` |  |  |
| G06 | G06 | Recovery/account lifecycle | Retain local PASS and external provider hold | `EXTERNAL` |  |  |
| G07 | G07 | Mind/Brain/Agentend | Run exact-main D-G and loop proofs | `ALREADY_PROVEN` |  |  |
| G08 | G08 | Billing/entitlement | Keep provider/UI disposition explicit | `EXTERNAL` |  |  |
| G09 | G09 | Glow/progression | Audit current applicable Glow scope | `CURRENT_REQUIREMENT` |  |  |
| G1 | G | Prediction and outcome reconciliation | PASS-CANDIDATE | `d012c5429bd035deb8a89b7fe19deb49c111356c` | NONE | None |
| G10 | G10 | Systems/Universe | Reconcile against current six-System authority | `SUPERSEDED` |  |  |
| G11 | G11 | Localization/RTL | Retain human-review hold; run deterministic diagnostics | `EXTERNAL` |  |  |
| G12 | G12 | Community | Audit current route scope and remaining gaps | `CURRENT_REQUIREMENT` |  |  |
| G13 | G13 | Group Research | Document local-only authority and external fetch hold | `SUPERSEDED` |  |  |
| G14 | G14 | Projects/Files/Agents/Capsules/Omega | Run exact-main project/capsule/agent matrix | `CURRENT_REQUIREMENT` |  |  |
| G15 | G15 | Ops/observability/backup/restore/recovery | Run isolated backup/restore/crash and classify staging external | `CURRENT_REQUIREMENT` |  |  |
| G16 | G16 | Exact release artifact/fresh extract | Complete exact-main artifact after gates | `CURRENT_REQUIREMENT` |  |  |
| G2 | G | Belief change candidate | NOT_PROVEN | `and model-generated claim review paths are covered` | 184 D–G tests passed | 184 D–G tests passed |
| G3 | G | WhyChanged linkage | NOT_PROVEN | `and superseded chain` | 184 D–G tests passed | 184 D–G tests passed |
| G4 | G | Memory candidate effect proof | PASS-CANDIDATE | `d012c5429bd035deb8a89b7fe19deb49c111356c` | NONE | None |
| G5 | G | Hardness signal ingestion | NOT_PROVEN | `184 D–G tests passed` | apps/api/app/tests/test_hardness_db_rls.py; apps/api/app/tests/test_hardness_e2e.py | apps/api/app/tests/test_hardness_db_rls.py; apps/api/app/tests/test_hardness_e2e.py |
| G6 | G | Held-out and shadow evaluation | PASS-CANDIDATE | `d012c5429bd035deb8a89b7fe19deb49c111356c` | NONE | None |

## Reconciliation rules

Historical PASS records whose evidence SHA is not the current canonical main are represented as `PASS-CANDIDATE`, not silently promoted to PASS. The current main SHA is `caf58863e93b47b4c148c11d86efdd1245354ef1`; after exact-main reruns, rows will be updated only with command-level evidence. External and founder-authority rows remain explicitly separate from internally solvable gaps.
