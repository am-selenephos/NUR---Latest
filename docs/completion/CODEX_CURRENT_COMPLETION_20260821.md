# NUR Current Completion - 2026-08-21

## Snapshot

```text
repository: am-selenephos/NUR---Latest
base main: 1c6f5f1e9f3380204f6809d2a78364e046e4908e
branch: codex/nur-final-closure-20260820
baseline SHA assessed: 633acc9d5567de92a802a691570afec253a39123
PR: #5 (open draft)
baseline exact-head CI: 32434716378 (success)
worktree: closure candidate changes in progress; see the final closure ledger
```

This is the pre-closure baseline re-score of the 82 top-level tasks in
`NUR_FULLSTACK_AGENTEND_MASTER_ADDENDUM_20260814.md`. It does not carry
mock-backed browser behavior, source existence, historical receipts, or
evidence from another SHA forward as full verification.

## Scoring

- `VERIFIED`: implementation and requirement-appropriate proof exist.
- `PARTIAL`: meaningful implementation exists, but required proof or behavior
  remains internally solvable.
- `INTERNAL_BLOCKED`: no safe internal path is currently available.
- `EXTERNAL_BLOCKED`: an external provider, reviewer, or unavailable runtime is
  required.
- `FOUNDER_DECISION`: the action changes protected release state.
- `SUPERSEDED`: the literal path is stale, but a documented canonical
  replacement satisfies the same requirement.

Strict completion counts `VERIFIED` and `SUPERSEDED`. Weighted completion gives
`PARTIAL` one half point. Blocked and founder-decision rows receive zero.

## Exact 82-task matrix

| Phase | Task | Requirement | Implementation location | Test/evidence | Exact SHA | Status | Missing proof | Internal/external | Next action |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A | A1 | Environment and Git truth | Git/GitHub; `docs/completion/CODEX_SOURCE_AUTHORITY.md` | live `git status`, worktree, PR and CI queries | `633acc9` | PARTIAL | tracked authority document still names stale repository/SHAs | Internal | replace stale authority with current source-truth receipt |
| A | A2 | Resolve celestial candidate branch | `docs/completion/MANUS_PHASE_A_BRANCH_RECONCILIATION.md` | classified file-level reconciliation; targeted V197 tests | `633acc9` | VERIFIED | none | Internal | retain evidence and preserve selected ports |
| A | A3 | Isolated canonical integration worktree | current closure worktree from protected main | `git worktree list`; clean branch based on `origin/main` | `633acc9` | SUPERSEDED | requested worktree name is stale; closure worktree is canonical equivalent | Internal | document supersession in source authority |
| A | A4 | Donor inventory | `docs/completion/CODEX_REPOSITORY_HYGIENE.csv`; branch reconciliation | branch/file inventories | `633acc9` | VERIFIED | none | Internal | keep donor read-only |
| A | A5 | Public-safety audit | `infra/scripts/secret-scan.sh`; V197 boundary probes | secret scan and direct-provider/runtime checks pass | `633acc9` | VERIFIED | none | Internal | rerun on final SHA |
| B | B1 | Route/client contract matrix | `docs/completion/MANUS_ROUTE_CLIENT_CONTRACT_MATRIX.csv` | 144 client operations covered by 420 OpenAPI operations | `633acc9` | VERIFIED | none | Internal | keep drift gate in CI |
| B | B2 | Agent retry contract | `v197ApiClient.ts`; `v197Adjuncts.ts` | `agentic-contract.test.ts`; API retry tests | `633acc9` | VERIFIED | none | Internal | preserve immutable successor semantics |
| B | B3 | Approval EDIT | Agent API/client/UI and runtime | API approval tests; agentic browser contract tests | `633acc9` | VERIFIED | none | Internal | include in real-stack route suite |
| B | B4 | Talk capability and memory mode | `v197StreamClient.ts`; Talk API | stream-client unit tests; API validation tests | `633acc9` | VERIFIED | none | Internal | retain fail-closed defaults |
| B | B5 | OpenAPI drift gate | `check_openapi_drift.py`; readiness workflow | local and exact-head CI pass | `633acc9` | VERIFIED | none | Internal | keep deterministic CI gate |
| B | B6 | Full-stack gateway read/write proof | `apps/web/e2e/b6-gateway.spec.ts` | historical real-stack browser receipt | `633acc9` | PARTIAL | no exact-current-SHA fresh real-stack rerun | Internal | fold into deterministic real-stack CI lane |
| C | C1 | Talk answer-only E2E | Talk SSE, Mind/Brain, durable turns | API vertical tests; disabled-provider browser path | `633acc9` | PARTIAL | no deterministic server-provider answer/replay/cancel V197 proof | Internal | add test provider behind server boundary and real-stack E2E |
| C | C2 | Talk workflow proposal E2E | Mind agency bridge and workflow compiler | API Mind/Brain tests | `633acc9` | PARTIAL | no V197-driven real-stack proposal proof | Internal | drive explicit Talk action through browser control |
| C | C3 | Approval E2E | approval service, ledger, outbox | HTTP/DB atomicity tests; mocked V197 control proof | `633acc9` | PARTIAL | no real browser APPROVE/EDIT/REJECT matrix | Internal | add real-stack V197 decision suite |
| C | C4 | Beat/worker E2E | Celery beat, dispatcher, worker, outbox | real Redis and separate Celery subprocess tests | `633acc9` | VERIFIED | none | Internal | rerun on final SHA |
| C | C5 | Verified-result UI E2E | Agent events and V197 agent detail | real worker test creates workflow through direct browser fetch | `633acc9` | PARTIAL | workflow is not created through intended V197 control | Internal | replace direct fetch setup with UI-driven flow |
| D | D1 | CognitiveTaskPacket audit | `brain/schemas.py` | `test_addendum_dg_contracts.py` | `633acc9` | VERIFIED | none | Internal | retain context-family acceptance test |
| D | D2 | User/Self/World composition | Mind context and capability hydrator | Mind/Brain capability tests | `633acc9` | VERIFIED | none | Internal | preserve canonical stores |
| D | D3 | Belief and counterevidence composition | durable cognition claims plus `mind/beliefs.py` | belief and Omega tests | `633acc9` | PARTIAL | non-persistent parallel belief lifecycle duplicates authority | Internal | retire or bind duplicate implementation to canonical claims |
| D | D4 | Goals/intention arbitration | Brain router and Mind loop | explicit-action versus answer tests | `633acc9` | VERIFIED | none | Internal | retain owner-intent precedence |
| D | D5 | Context manifest | packet schemas and hydrator | Addendum D-G contract tests | `633acc9` | VERIFIED | none | Internal | keep included/excluded lineage |
| D | D6 | Cross-owner and token budgets | scoped DB, RLS, hydration budgets | DB isolation and budget tests | `633acc9` | VERIFIED | none | Internal | rerun final DB suite |
| E | E1 | Versioned packet/result contracts | `brain/schemas.py` | Addendum D-G contract tests | `633acc9` | VERIFIED | none | Internal | preserve v2 compatibility |
| E | E2 | Hardened Brain router | `brain/router.py` | route/budget decision tests | `633acc9` | VERIFIED | none | Internal | retain persisted decision lineage |
| E | E3 | Typed Planner | `brain/planner.py` | typed proposal tests | `633acc9` | VERIFIED | none | Internal | preserve bounded output |
| E | E4 | Bounded Simulator | `brain/planner.py` | budget comparison tests | `633acc9` | VERIFIED | none | Internal | preserve limits |
| E | E5 | Validator and independent critic | `brain/critic.py` | distinct-role contract tests | `633acc9` | VERIFIED | none | Internal | keep critic non-mutating |
| E | E6 | Research Brain | `brain/research.py`; in-memory adapter | citation and contradiction tests | `633acc9` | PARTIAL | no governed retrieval adapter; only supplied evidence is evaluated | Internal plus external retrieval | implement provider-neutral retriever contract; external fetch stays blocked |
| E | E7 | Specialist workers | `brain/specialists.py` | scope and budget tests | `633acc9` | VERIFIED | none | Internal | preserve capability scoping |
| E | E8 | Evaluation corpus | `brain/evaluation.py` | current corpus/evaluation tests | `633acc9` | PARTIAL | expected PASS values are generated by the same evaluator | Internal | use frozen independent observations and failure cases |
| F | F1 | Hydration tier parity | capability hydrator and Mind context | semantic hydration tests | `633acc9` | VERIFIED | none | Internal | preserve approved-source policy |
| F | F2 | Worker DAG limits | `agentic/limits.py`; compiler | width/depth/cost/deadline tests | `633acc9` | VERIFIED | none | Internal | retain bounded execution |
| F | F3 | Safe event parity | `v197CapabilityReducer.ts` | reducer allowlist tests | `633acc9` | VERIFIED | none | Internal | keep raw payloads stripped |
| F | F4 | WorkflowProposalV2 | packet schema and Agency bridge | semantic proposal tests | `633acc9` | VERIFIED | none | Internal | keep one Agency path |
| F | F5 | Plan-from-conversation production proof | Talk, Agency, canonical Plan store | browser proof intercepts Talk/approval/Plans | `633acc9` | PARTIAL | no real API/DB preview-save-approval-reload proof | Internal | add real-stack V197 Plan lifecycle |
| G | G1 | Prediction/outcome reconciliation | learning outcome loop | Omega/outcome tests | `633acc9` | VERIFIED | none | Internal | rerun final learning suite |
| G | G2 | Belief change candidate | learning and correction services | learning/correction tests | `633acc9` | VERIFIED | none | Internal | preserve owner review |
| G | G3 | WhyChanged linkage | `mind/why_changed.py`; `omega/why_changed_service.py` | WhyChanged and Omega tests | `633acc9` | PARTIAL | Omega synthesizes a second explanation path instead of canonical ledger query | Internal | route all explanations through one append-only authority |
| G | G4 | Memory candidate effect proof | memory candidate service | cognition/hardness tests | `633acc9` | VERIFIED | none | Internal | extend into real Talk continuity route proof |
| G | G5 | Hardness ingestion | learning hardness signals | DB/RLS and E2E tests | `633acc9` | VERIFIED | none | Internal | retain idempotency |
| G | G6 | Held-out/shadow evaluation | `brain/evaluation.py` | promotion-gate tests | `633acc9` | PARTIAL | corpus is not independently frozen or empirically separated | Internal | add immutable observations and shadow comparison receipts |
| H | Today | Complete owner route | living API and V197 Today | API tests; mocked/full-interface navigation | `633acc9` | PARTIAL | real check-in mutation/reload/error/mobile/a11y matrix | Internal | add to two-owner real-stack route suite |
| H | Talk | Complete owner route | Talk API/SSE and V197 Talk | API tests; disabled-provider browser test | `633acc9` | PARTIAL | deterministic answer/replay/cancel and error/mobile/a11y proof | Internal; live provider is J6 | add server-side deterministic provider fixture |
| H | Journal | Complete owner route | cognition Journal API and V197 Journal | API persistence tests; mocked control tests | `633acc9` | PARTIAL | unmocked create/edit/archive/reload/error/mobile/a11y proof | Internal | add real-stack lifecycle |
| H | Plan | Complete owner route | cognition Plan API and V197 Plan | API tests; mocked F5 browser test | `633acc9` | PARTIAL | unmocked create/edit/steps/outcome/reload/owner denial | Internal | add real-stack lifecycle |
| H | Systems | Complete owner route | living Systems API and V197 field | API/catalog and browser visual tests | `633acc9` | PARTIAL | fresh owner selection/mutation/reload/error/a11y proof | Internal | add real-stack lifecycle |
| H | Orbit | Complete owner route | `orbit_world.py`; `v197Orbit.ts` | API tests; historical browser matrix | `633acc9` | PARTIAL | deterministic owner relation fixture and clean route run | Internal | seed relation and run mobile/a11y/reload proof |
| H | Map | Complete owner route | Map APIs and `v197Map.ts` | API tests; historical browser matrix | `633acc9` | PARTIAL | confirmed-edge fixture and real correction/reload proof | Internal | seed edge and close route matrix |
| H | Timeline | Complete owner route | Timeline API and `v197Timeline.ts` | API tests; historical partial browser sweep | `633acc9` | PARTIAL | unskipped real-stack ordering/isolation/mobile/a11y suite | Internal | run clean deterministic fixture |
| H | Insights | Complete owner route | Insights APIs and dedicated V197 surface | API tests; mocked seeded-review browser test | `633acc9` | PARTIAL | real confirm/correct/reject/proposal/reload/error proof | Internal | add real-stack lifecycle |
| H | Agents | Complete owner route | Agent APIs and V197 Agency UI | DB/worker tests; mocked owner UI | `633acc9` | PARTIAL | real browser workflow/detail/polling/decision/retry matrix | Internal | add real-stack lifecycle |
| H | Memory | Complete owner route | Memory API and V197 adjunct | API tests; mocked owner-product suite | `633acc9` | PARTIAL | two-owner approve/correct/retire/reload/context-use proof | Internal | add continuity lifecycle |
| H | Projects | Complete owner route | Projects/files/runs APIs and V197 adjunct | API/storage tests; mocked deliverables UI | `633acc9` | PARTIAL | real upload/approval/artifact/verifier/reload/denial proof | Internal | add real-stack project lifecycle |
| H | Capsules | Complete owner route | Capsules API and V197 controls | API tests; conflicting historical browser receipts | `633acc9` | PARTIAL | 10 clean no-retry two-account cycles plus mobile/error states | Internal | debug and repeat exact lifecycle |
| H | Research | Complete local owner route | local briefs/jobs/sources API and V197 client | local API and mocked UI tests | `633acc9` | PARTIAL | real local brief persistence/reload/error proof | Internal; live retrieval external | close local contract only; retain retrieval hold |
| H | Community | Complete bounded owner route | Community APIs and V197 adjunct | multi-owner API tests; mocked browser path | `633acc9` | PARTIAL | real room/message/reload/denial/abuse/error proof | Internal | add deterministic browser lifecycle |
| H | Billing | Complete internal owner route | Billing APIs, entitlements, V197 checkout | API tests; mocked checkout fallback | `633acc9` | PARTIAL | real internal entitlement/webhook idempotency browser projection | Internal; sandbox transaction external | close internal route; retain sandbox hold |
| H | Notifications | Complete internal owner route | notification API and V197 controls | API persistence/RLS tests; mocked browser reload | `633acc9` | PARTIAL | real event/read/mark-read/reload/error/mobile/a11y proof | Internal | add real-stack lifecycle |
| H | Localization | Complete machine-verifiable route | translations/profile/i18n/RTL | translation tests; mocked settings proof | `633acc9` | PARTIAL | real locale persistence, fallback, RTL overflow and a11y matrix | Internal; human language review external | close deterministic behavior and publish human-review hold |
| I | I1 | RLS matrix | forced-RLS migrations and DB policies | cross-owner DB suite | `633acc9` | VERIFIED | none | Internal | rerun final DB suite |
| I | I2 | CSRF/origin matrix | mutation security and API middleware | generated mutation matrix; exact-head CI | `633acc9` | VERIFIED | none | Internal | retain route inventory gate |
| I | I3 | Agent replay attacks | approval digest/version/call version | agentic replay/idempotency tests | `633acc9` | VERIFIED | none | Internal | rerun final security suite |
| I | I4 | Prompt/tool injection corpus | Brain/Research/Agency boundaries | injection and capability tests | `633acc9` | VERIFIED | none | Internal | add malicious external-evidence browser/API case |
| I | I5 | GitHub Actions hardening | pinned actions and minimal permissions | workflow inspection and exact-head CI | `633acc9` | VERIFIED | none | Internal | retain immutable action SHAs |
| I | I6 | Main branch protection | GitHub branch protection | live API: strict checks, PR, admins, no force push/delete | `633acc9` | VERIFIED | none | Founder/admin state | recheck before promotion |
| I | I7 | Dependencies and SBOM | dependency locks, audits, tracked SBOMs | npm audit pass; SBOM freshness scripts | `633acc9` | PARTIAL | tracked SBOM provenance names `1c6f5f1`, not current SHA | Internal | generate CI artifact SBOM bound to tested SHA |
| J | J1 | Cold boot | Compose/bootstrap/fresh-extract scripts | historical boot evidence | `633acc9` | PARTIAL | production web host and exact-SHA fresh boot receipt | Internal | implement static host and run isolated cold boot |
| J | J2 | Backup | DR backup scripts and manifest | contract/unit tests; older receipt | `633acc9` | PARTIAL | exact-SHA isolated backup receipt and object parity | Internal; production storage external | run local isolated backup |
| J | J3 | Restore drill | DR restore/drill scripts | contract tests; older receipt | `633acc9` | PARTIAL | exact-SHA restore parity with RPO/RTO | Internal; production storage external | run isolated restore drill |
| J | J4 | Crash/recovery A-D | runtime recovery drill script | script contract tests | `633acc9` | PARTIAL | actual PID/timestamp/state/effect receipts for all four scenarios | Internal | execute controlled real-process drill |
| J | J5 | Static release gate | readiness and release-gate scripts | current CI covers only selected deterministic gates | `633acc9` | PARTIAL | release package/SBOM/fresh-extract gates absent from exact-head CI | Internal | add stable release lane |
| J | J6 | Live provider gate | server provider boundary | provider-disabled honest proof | `633acc9` | EXTERNAL_BLOCKED | approved server-side credential and eligible model | External | run only when approved secret/model are available |
| J | J7 | Real-stack browser matrix | real-stack Playwright specs exist | historical receipts; CI browser tests are mocked | `633acc9` | PARTIAL | deterministic exact-SHA full-stack browser lane | Internal | build isolated real-stack fixture and CI job |
| J | J8 | Cross-browser, accessibility, performance | WebKit/a11y/performance specs | historical WebKit matrix has unresolved failure | `633acc9` | PARTIAL | clean Chromium/WebKit, axe, reduced-motion, lifecycle and soak receipt | Internal; macOS Safari external | repair and run internal matrix |
| J | J9 | Fresh-extract artifact | package and verifier scripts | contract tests; old-SHA evidence | `633acc9` | PARTIAL | exact-SHA HOLD artifact, SBOM, parity, boot receipt | Internal | build and independently verify candidate artifact |
| J | J10 | Independent final review | `INDEPENDENT_REVIEW_PACKET.md` | packet exists but explicitly is not approval | `633acc9` | EXTERNAL_BLOCKED | independent reviewer verdict | External | prepare final packet, then request independent review |
| K | K1 | Final integration PR | GitHub PR #5 | open draft PR at exact branch head | `633acc9` | VERIFIED | readiness promotion waits on internal closure | Internal | keep draft until internal unresolved is zero |
| K | K2 | Exact-head CI | NUR Readiness run `32434716378` | API and web/security jobs pass | `633acc9` | VERIFIED | future changes require a new exact-head run | Internal | rerun after closure commits |
| K | K3 | Merge | protected GitHub main | not executed | `633acc9` | FOUNDER_DECISION | independent approval and founder promotion authority | Founder | merge only after approval |
| K | K4 | Main CI | GitHub Actions on main | cannot occur before merge | `633acc9` | FOUNDER_DECISION | K3 | Founder | run on exact merged main SHA |
| K | K5 | Annotated tag | Git tag/release | not executed | `633acc9` | FOUNDER_DECISION | founder release approval and exact artifact | Founder | tag only after explicit approval |
| K | K6 | Repository rename runbook | `docs/completion/MANUS_REPOSITORY_RENAME_RUNBOOK.md` | runbook inspection | `633acc9` | VERIFIED | actual rename is optional founder/business action | Founder | do not rename without explicit approval |

## Counts

```text
TOTAL_TASKS=82
VERIFIED=37
PARTIAL=39
INTERNAL_BLOCKED=0
EXTERNAL_BLOCKED=2
FOUNDER_DECISION=3
SUPERSEDED=1

STRICT_COMPLETION_PERCENT=46.3
WEIGHTED_COMPLETION_PERCENT=70.1
INTERNAL_UNRESOLVED=39
```

The previous approximately 84-85 percent score was not retained because it
treated several mock-backed Phase-H browser checks and historical J receipts as
full or half-closed without applying every route requirement to the exact SHA.
The current 70.1 percent weighted score is the honest execution baseline, not a
claim that prior code was lost.

## First internal closure targets

1. Remove duplicate belief and WhyChanged authorities.
2. Establish a deterministic real-stack two-owner Playwright harness and close
   route lifecycles without API interception.
3. Replace the Vite development container with a production static web-serving
   path that preserves same-origin API/session/CSRF behavior.
4. Execute J1-J4 and J9 on one exact candidate SHA and retain receipts.
5. Generate SHA-bound SBOMs as CI artifacts and expand stable release gates.

Current truthful verdict: `NUR_FINAL_HOLD`.
