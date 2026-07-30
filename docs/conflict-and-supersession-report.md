# Conflict And Supersession Report

Date: 2026-07-11

| Older requirement or implementation | Latest founder decision | Result in this repository |
|---|---|---|
| Recreate V197 as React routes/components | Canonical V197 DOM/CSS/runtime owns presentation | React visual routes are bypassed; `#root` is absent from product pages. |
| Phase 1 write guard disabled all canonical writes | Track A requires a sellable persisted owner loop | Auth, Talk, Journal, Plan, Outcome, Glow, Research staging, and preferences use the thin bridge and FastAPI. |
| Static V197 fake counts and candidate advice | No fake live metrics or invented insights | Owner-ledger endpoints hydrate counts; candidate panel uses persisted claims or an honest empty state. |
| Preserve canonical geometry even where broken | Do not preserve V197 defects as sacred | Canonical bytes remain unchanged; bridge-scoped polish fixes overlap, clipped tabs, and mobile control rows. |
| Anti-engagement interpretation that removed rewards | Glow/streak/quest/level mechanics are founder scope | Core server Glow transactions and one basic streak exist; quests/levels remain Track B and are not claimed. |
| Korean treated as the only special language | All 35 locales matter; Korean remains core | 35 slots exist, Korean is `ko` / `한국어`; only selected Track A copy is translated. |
| Roman Urdu as a separate locale | Urdu locale plus writing preference | `locale=ur`, `writing_preference=roman`, `dir=ltr`. |
| Capsule/Settings/Omega React adjuncts | Missing surfaces must be V197-native plain DOM | Their visual routes remain honest 404s in Track A; backend services are preserved. |
| Disabled AI response presented as chatbot success | Disabled mode never counts as chatbot proof | UI says provider is not connected; no real-model claim is made in this packet. |
| Direct Glow button | Glow follows persisted Outcome/action only | `/glow/rewards` is idempotent and source-gated; owner journey proves no visual reward before server success. |

## Winning authority order

1. Latest current-conversation founder instruction and Ultimate Founder Master Prompt.
2. Canonical V197 presentation/runtime.
3. Verified current repository and runtime evidence.
4. Existing backend/security contracts.
5. Older prompts only where non-conflicting.


---

# SOL 5.6 audit — conflicts requiring founder resolution

Date: 2026-07-30
Auditor: implementation agent, per SOL 5.6 §0 conflict law and §0.1 mandatory source reading.
Audited from: `/home/nur/.cache/nur-full-completion-20260726`, branch
`claude/nur-agentic-spine-20260728` @ `e833062`, clean tree, migrations at `0049`.

These are recorded rather than reconciled, as §0 requires. Four are blocking:
implementing SOL 5.6 §5 against the wrong renderer or the wrong worktree would
destroy proven work.

## CONFLICT-005 — three divergent working copies, and the gate ledger is not in the newest

| field | value |
|---|---|
| conflict_id | CONFLICT-005 |
| older_requirement | `docs/integration/v5-completion/STATE.json` names `/home/nur/NUR-INTEGRATION-20260722`, branch `completion/nur-v5-full-pass`, `migration_head 0030`, updated 2026-07-25 |
| newer_requirement | SOL 5.6 §0.1: "Inspect the current working repository, not an older extracted copy" |
| winner | **UNRESOLVED — founder decision required** |
| reason | Three copies exist and none dominates on every axis. `…/nur-full-completion-20260726` has the newest commit (2026-07-30) and migrations `0049`; `NUR-INTEGRATION-20260722` (2026-07-27, migrations `0031`) holds the gate ledger, `GATE_MATRIX.csv`, evidence runs, and the renderer the e2e specs assert; `NUR-LIVE-TALK-PROOF-20260723` holds the LIVE_TALK_PASS proof and is 8 files dirty. Choosing wrong strands either the Agency Plane (19 migrations, PR #11) or the gate evidence. |
| affected_surfaces | every surface — this decides where all SOL 5.6 work lands |
| affected_data | migrations `0032`–`0049`, gate evidence dirs, LIVE_TALK proof |
| affected_tests | full API suite (663 here), all gate runners, all Playwright evidence |
| resolution_status | BLOCKING |

## CONFLICT-006 — SOL 5.6 §5.2 renderer identity matches no renderer that exists

| field | value |
|---|---|
| conflict_id | CONFLICT-006 |
| older_requirement | SOL 5.6 §5.2: renderer is exactly 27,655 bytes, SHA-256 prefix `c5218640`, suffix `7c242`, 1,060 stars, 978 connections; "do not casually regenerate, simplify, replace, or overwrite it" |
| newer_requirement | Verified bytes on disk |
| winner | **UNRESOLVED — founder decision required** |
| reason | No file of 27,655 bytes exists in any worktree, and no revision of `apps/web/src/bridge/v43StarBrainRuntime.js` in its eight-commit history has a SHA-256 beginning `c5218640`. Actual renderers: `…20260726` 29,165 B `680f15da…aacbe` (`b32189b`); `…20260722` 25,145 B `8e249a70…34192` (`d6a9d1b`); `…20260723` 18,883 B `ee34405b…8d347` (`f265123`). The literals 1060/978/2086/1355 do not appear in the current renderer; only the stem counts 147 and 97 do. So §5.2's preservation target cannot be identified, and "preserve it exactly" is currently unexecutable. |
| affected_surfaces | landing hero, Systems/Universe identity, star-brain identity pass |
| affected_data | none |
| affected_tests | `v197-star-brain.spec.ts`, `v197-runtime-lifecycle.spec.ts`, `v43-star-brain-source.test.ts`, `phase1-host.test.ts` |
| resolution_status | BLOCKING |

## CONFLICT-007 — two e2e specs pin a renderer five commits stale

| field | value |
|---|---|
| conflict_id | CONFLICT-007 |
| older_requirement | `v197-star-brain.spec.ts` and `v197-runtime-lifecycle.spec.ts` assert renderer SHA `8e249a70…34192` |
| newer_requirement | The renderer is `680f15da…aacbe`, which `v197StarBrain.ts`, `v43-star-brain-source.test.ts` and `phase1-host.test.ts` already expect |
| winner | repository (the app is self-consistent; the two specs are stale) |
| reason | `8e249a70` is the renderer at `d6a9d1b`. Five later commits changed it — `84b66a2`, `06a40fb`, `0cc01ff`, `3a60994`, `d383b75`, `b32189b` — each updating the bridge and unit tests but never these two specs. So they have been failing since `84b66a2`, not merely since the palette change. Six specs fail now: 2 assertions × 3 projects. Direction of the fix is founder's: if `b32189b` ("take the cool colours out of the star brain palette") was intended, update the specs to `680f15da`; if the cool-coloured brain was correct, `b32189b` is a regression to revert. |
| affected_surfaces | landing hero, Systems map star brain |
| affected_data | none |
| affected_tests | 6 failing Playwright specs across chromium-desktop, chromium-mobile, webkit-mobile |
| resolution_status | AWAITING FOUNDER DIRECTION (two-way, both mechanical) |

## CONFLICT-008 — gate ledger is six days stale and contradicts the reported state

| field | value |
|---|---|
| conflict_id | CONFLICT-008 |
| older_requirement | `GATE_MATRIX.csv`, evidence run `20260724T225447Z`: zero gates PASS; `G12_COMMUNITY` 1 PASS / 10 PARTIAL / 3 MISSING → `BLOCKED_EXTERNAL` |
| newer_requirement | SOL 5.6 §1: overall ≈70%, current gate `G12` ≈95%, star-brain production 0% |
| winner | neither is currently provable |
| reason | The matrix predates this repository's last 19 migrations and its whole Agency Plane, so it cannot describe present state. The ≈95% figure is a status estimate that §1 itself says is "not proof". The matrix's own `NEXT_ACTION.md` says six gates were `BLOCKED_EXTERNAL` only because the API stack was not running — which it now is (`/healthz` healthy, live loop clean). A fresh gate run is required before any percentage is asserted. §1 forbids both lowering proven progress and faking completion, so no number is claimed here. |
| affected_surfaces | all gate reporting |
| affected_data | evidence directories |
| affected_tests | every gate runner under `infra/scripts/nur-gate.sh` |
| resolution_status | NEEDS FRESH EVIDENCE RUN (not a founder decision) |

## CONFLICT-009 — §4.2 canonical host hash restates a superseded value

| field | value |
|---|---|
| conflict_id | CONFLICT-009 |
| older_requirement | SOL 5.6 §4.2 cites canonical V197 hash `252eee806ece31ef829a2dc5cd45aa8d8f8e855db1bde98b6f87193d786633c3` |
| newer_requirement | Repository canonical host hashes to `d4f7f2d3e4c8e36dfc0c6edd51a028f28a04afbc2afa434a319009cb2f122bc6` |
| winner | repository — and §4.2 anticipates this ("Do not trust a copied hash alone. Recalculate it from current source.") |
| reason | Already recorded as CONFLICT-001: commit `f8ddd7a` (2026-07-18) rebuilt the canonical host after the plan lock. `infra/scripts/check-v197-integrity.sh` returns `"pass": true` with host, entry and universe all byte-identical to expectation, so canonical integrity currently holds against the repository baseline. No action beyond keeping §4.2's own recalculation rule. |
| affected_surfaces | canonical host, entry stage, universe stage |
| affected_data | none |
| affected_tests | `check-v197-integrity.sh` |
| resolution_status | RESOLVED — repository baseline stands |

---

# NUR Map spec audit — conflicts requiring founder resolution

## CONFLICT-010 — Map spec names seven Systems; the repository has six founder-locked

| field | value |
|---|---|
| conflict_id | CONFLICT-010 |
| older_requirement | `apps/api/app/living/catalog.py` — docstring "Founder-locked definitions for NUR's **six** Star Systems", slugs `ambition`, `rebuild`, `creation`, `growth`, `introspection`, `connection`. `app/services/auth_service.py` `CORE_SYSTEMS` agrees exactly (same six, same names) and seeds one Orbit per System at registration. |
| newer_requirement | Map spec §3.1 and §41 acceptance criterion 1: **seven** Systems — Quiet Ambition, Rebuild, Study, Money, Body, Connection, Creation. |
| winner | **not resolved — founder decision required.** |
| reason | The two lists agree on only four concepts (`ambition`≈Quiet Ambition, `rebuild`, `connection`, `creation`). The spec drops `growth` and `introspection` and adds three Systems that do not exist anywhere in the repository: **Study**, **Money**, **Body**. This is not a labelling difference. `system_slug` is a plain `varchar(48)` carried on `goals`, `objectives`(via goal), `system_actions`, `scheduled_actions`, `system_diagnostics` and `feasibility_assessments`, and every existing owner already has six seeded Orbits keyed to the six slugs. Adding or renaming Systems would (a) require a data migration for every existing owner's rows, (b) require six new founder-authored `SystemDefinition` blocks — each needs `definition`, 6–7 `questions`, a `checklist`, `ignored_prediction` and `followed_prediction`, all of which are founder voice and cannot be invented by an implementer, and (c) contradict the word "Founder-locked" in the file itself. I will not silently rewrite founder-locked content, and I will not fabricate the missing definitions. |
| affected_surfaces | Map (System regions), Systems page, Today, registration seeding, `/api/v1/map` graph |
| affected_data | `goals.system_slug`, `system_actions.system_slug`, `scheduled_actions.system_slug`, `system_diagnostics.system_slug`, `feasibility_assessments.system_slug`, seeded `orbits` rows |
| affected_tests | `app/tests/test_sol_living_system.py` (`SYSTEM_SLUGS` is asserted against the catalog and against `/api/v1/map` node ids) |
| resolution_status | **OPEN — founder decision.** Implementation taken meanwhile: the Map renders System regions **driven from the canonical catalog** rather than a hardcoded list, so it displays whatever `SYSTEMS` contains and will pick up a seventh automatically the moment the founder adds it. Consequence to be honest about: acceptance criterion 1 ("Seven Systems appear as meaningful regions") currently renders **six** regions, and cannot be met without this decision. |

### Noted while auditing, not a conflict

`_stable_layout` in `app/api/v1/map.py` already distributes System nodes with
`2 * math.pi / 7` while the catalog holds six, so the existing graph leaves a
one-seventh gap in the ring. That is consistent with seven having been intended
at some point, which is why this is recorded rather than assumed either way.

## Audit notes

- The SOL 5.6 instruction as received is **truncated** mid-sentence in §28.4
  (`false verified cl…`). The complete PASS-blocker list and every section after
  it are unavailable, so no PASS verdict can be claimed against §28.4 until the
  remainder is supplied.
- Nothing in this audit changed any product code.
