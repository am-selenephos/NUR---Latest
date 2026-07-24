# Conflict and supersession report — V6

Recorded per Masterplan §0, which requires every implementation conflict to carry
`conflict_id / older_requirement / newer_requirement / winner / reason / affected_surfaces /
affected_data / affected_tests / resolution_status`.

---

## CONFLICT-001 — canonical V197 source hash

- **conflict_id:** CONFLICT-001
- **older_requirement:** Masterplan V5 §9.1 (lines 1243–1249) and Masterpack manifest
  `canonical_v197_checkpoint.sha256` pin canonical V197 to
  `252eee806ece31ef829a2dc5cd45aa8d8f8e855db1bde98b6f87193d786633c3`.
- **newer_requirement:** the repository pins and gate-enforces
  `d4f7f2d3e4c8e36dfc0c6edd51a028f28a04afbc2afa434a319009cb2f122bc6`
  in `scripts/check-v197-integrity.ts`.
- **winner:** repository state — **provisionally**, pending founder ratification.
- **reason:** the pre-rebuild blob at commit `6ce2c46` hashes to *exactly* the plan value, so
  the plan was accurate when written. Commit `f8ddd7a` (2026-07-18, five days after the plan
  lock) rebuilt the host with `apps/web/scripts/rebuild-v197-canonical.mjs`, which extracts the
  Base64 Entry/Universe documents, prunes dead legacy styles and scripts through JSDOM, and
  re-embeds them; size fell 1,029,176 → 718,041 bytes. That is Masterplan §9.6 "Stage S —
  static-source extraction" performed as designed, not a violation of the source law.
  However, product law allows a new canonical source only on explicit founder approval, and
  no such approval is recorded.
- **affected_surfaces:** Entry stage, Universe stage, all 90 registered V197 controls.
- **affected_data:** none — presentation source only, no user data.
- **affected_tests:** `scripts/check-v197-integrity.ts`, `npm run v197:integrity`, and every
  `apps/web/e2e/v197-*.spec.ts`.
- **resolution_status:** **OPEN** — blocker B1, `FOUNDER_ACTION_REQUIRED_CANONICAL_V197_HASH`.

---

## CONFLICT-002 — interaction registry vocabulary and totals

- **conflict_id:** CONFLICT-002
- **older_requirement:** Status ledger V5 §4.2 records a 45-control registry
  (33 `WIRED` / 7 `SOURCE_NATIVE` / 5 `HONEST_DISABLED`), and an older local reference
  registry of 110 controls (109 `WIRED` / 1 `HONEST_DISABLED`). The ledger states the two
  must never be merged or averaged.
- **newer_requirement:** `docs/release/v197-control-matrix.json` records **90** controls under
  a different vocabulary: `LIVE_REAL` 73, `INTENTIONAL_LOCAL_ONLY` 8,
  `NOT_IMPLEMENTED_VISIBLE` 7, `BLOCKED_BY_EXTERNAL_PROVIDER` 2, `DEAD`/`DUPLICATE`/
  `MISLEADING`/`BROKEN` 0.
- **winner:** the 90-control matrix — it is the later artifact and matches the current shell.
- **reason:** the three registries describe different presentation lineages. The V6 vocabulary
  is stricter: it separates "deliberately local" from "not implemented" from "blocked by an
  external provider", which the older `HONEST_DISABLED` bucket conflated.
- **affected_surfaces:** every V197 control.
- **affected_data:** none.
- **affected_tests:** `apps/web/e2e/v197-control-matrix.spec.ts`, `button-registry.spec.ts`.
- **resolution_status:** **PARTIALLY RESOLVED.** The matrix wins, but it is **STALE**: its
  `generated_from_sha` is `33a5dab` (the Live-Talk proof worktree), not `6d7eeef`. It must be
  regenerated on this candidate before any G03 verdict. Tracked as agent blocker A2.

---

## CONFLICT-003 — status ledger currency

- **conflict_id:** CONFLICT-003
- **older_requirement:** Status ledger V5 (2026-07-13) reports `AUTH_PRESENTATION_PASS` with
  overall `HOLD`, and marks Glow, seven Systems, community, Group NUR, consultations,
  projects, billing, translation and notifications as `MISSING`, `PLACEHOLDER` or `DESIGN_LOCKED`.
- **newer_requirement:** the candidate contains real implementations, migrations and passing
  tests for every one of those domains (migrations 0011–0030; 41 backend test modules;
  180 passing backend tests).
- **winner:** verified current implementation truth.
- **reason:** the ledger's own authority rule states it is "historical evidence, not permission
  to ignore newer verified implementation". The ledger was written against a different, older
  lineage (`NUR_auth_fix/NUR`) that its own §2 flags as unable to prove current state.
- **affected_surfaces:** the whole product ledger.
- **affected_data:** none.
- **affected_tests:** the entire backend suite.
- **resolution_status:** **RESOLVED.** Superseded by `REQUIREMENT_MATRIX.csv` (229 rows) and,
  once authored, `docs/v6/NUR_EXACT_STATUS_LEDGER_V6.md`. The V5 files are preserved unmodified
  as historical evidence.
  **Caution:** "implemented and unit-tested" is still not "product-complete". Six domains are
  `BACKEND_ONLY` and count as failing.

---

## CONFLICT-004 — sequencing of revenue versus intelligence

- **conflict_id:** CONFLICT-004
- **older_requirement:** earlier plans placed the commercial spine immediately after presentation.
- **newer_requirement:** Masterplan §33 (line 3787) states the founder "has now explicitly
  required intelligence and interface learning to be held first".
- **winner:** intelligence first — `G07_INTELLIGENCE` precedes `G08_REVENUE`.
- **reason:** explicit later founder decision.
- **affected_surfaces:** execution order only.
- **resolution_status:** **RESOLVED** — reflected in the gate order and in `NEXT_ACTION.md`.
