# NUR — build state and handoff

Written for whoever picks this up next (Codex, Fable, or a human). It records what
exists, exactly where it lives, why it is shaped the way it is, what is verified,
what is not built, and what is blocked on a founder decision.

**Read §11 before writing code.** It lists the traps that already cost real
debugging time in this repository. Several of them look like nothing and are not.

---

## 1. Identity

| field | value |
|---|---|
| Worktree | `/home/nur/.cache/nur-full-completion-20260726` |
| Branch | `claude/nur-agentic-spine-20260728` |
| Head | `2f3d8b5` (local == remote, clean tree) |
| Base | `f024e6b951b3d603b39ecbb7fd6bf16d01d0a373` |
| PR | `am-selenephos/NUR#11`, **draft**, do not merge |
| Scope since base | 66 commits · 122 files · +36,435 / −26 lines · 18 migrations |
| Alembic head | `0052_timeline_temporal_layer` |
| CI workflow | `.github/workflows/readiness.yml` — two jobs: `api`, `web-and-security` |

### Verified at head

| gate | result |
|---|---|
| API suite | **759 passed**, 0 skipped |
| Ruff | clean (`python -m ruff check app`) |
| Web typecheck | clean (`tsc --noEmit`) |
| Web unit | 87 passed (18 files) |
| Web build | clean |
| `check-v197-integrity.sh` | `"pass": true` |
| `secret-scan.sh` | clean |
| Playwright (chromium-desktop) | **52 passed** — Timeline 18, Map 19, Orbit 11, star-brain 4, lifecycle |

CI has **both** Postgres (`pgvector/pgvector:pg16`) and **Redis** (`redis:7`)
service containers. The real-broker E2E therefore **does run in CI** and passes —
`readiness.yml` log shows `test_real_broker_e2e_db.py ...` (three dots, three
tests). An earlier note in this repository claimed CI had no Redis and that the
real-broker test was unenforced. That was wrong; this line is the correction.

---

## 2. The architecture law (non-negotiable)

Canonical V197 owns the visible product. This is the single most important rule and
the one most easily broken by accident.

- The canonical document is `apps/web/public/v197/NUR_V197_CHECKBOX_TICK_RESTORED.html`.
  **Its bytes are never edited.** `infra/scripts/check-v197-integrity.sh` hashes
  host, entry and universe and must return `"pass": true`.
- No product page is owned by a React tree. `#root` must be absent on every product
  page; three e2e tests assert this.
- New surfaces are **plain DOM/SVG adjuncts** injected into the canonical document
  through the bridge (`apps/web/src/bridge/v197Bridge.ts`).
- Component trees from the specs (§29 Orbit, §38 Map, §58 Timeline) are preserved as
  **function decomposition**, not React components.

### The canonical shell, and where surfaces mount

```
BODY.universe-edition
├── DIV#nur-front-v61.nur-interior            z-index 10
│   └── DIV.nur-shell
│       ├── ASIDE.nur-rail                    left rail   (never touched)
│       └── MAIN.nur-main
│           ├── HEADER.nur-topbar             UNIVERSE · MAP · ORBITS · TIMELINE · INSIGHTS
│           └── SECTION.nur-viewport          ← surfaces mount HERE
│               ├── SECTION#page-systems.nur-page.active   hidden while a surface is mounted
│               └── DIV#nur-surface-host                    created by v197SurfaceHost
└── CANVAS#space3d                            z-index 280, mix-blend-mode: screen
```

`#space3d` is the galaxy. It is at z-index **280**, above the shell at **10**, and
blends with `screen` — which only ever *lightens*. That is why the starfield appears
over canonical content, and why a surface hosted inside the shell gets stars for
free.

**Do not** give a surface `position: fixed`, a z-index, or a background. See §11.1.

---

## 3. Subsystem 1 — the Agency Plane

Durable, auditable action: an owner objective becomes a workflow, passes policy and
risk, pauses for exact-call approval where required, commits a dispatch intent, is
drained by a registered Celery Beat dispatcher, executed by a registered worker
under a durable claim, verified, recorded, and driven to a truthful terminal state —
surviving crash, redelivery and recovery without a duplicate durable effect.

### Files

| path | lines | role |
|---|---|---|
| `apps/api/app/agentic/` | 4,790 | the whole plane (18 modules) |
| `apps/api/app/agentic/orchestrator.py` | | state machine, `claim_step`, `transition_step`, `record_event`, `reclaim_expired_steps` |
| `apps/api/app/agentic/runtime.py` | | executes a step: split transaction, tool-version gate, policy gate, timeout ceiling |
| `apps/api/app/agentic/dispatcher.py` | | drains the outbox through the SECURITY DEFINER boundary |
| `apps/api/app/agentic/aggregate.py` | | single `aggregate_workflow()` — the one place workflow status is derived |
| `apps/api/app/agentic/policy.py`, `policy_store.py` | | spend ceilings, quiet hours (owner timezone via `zoneinfo`) |
| `apps/api/app/agentic/decisions.py` | | approve / reject / edit, with `_validate_before_queue()` |
| `apps/api/app/agentic/input_schemas.py` | | explicit per-tool field schemas for all 18 bound tools |
| `apps/api/app/agentic/handlers.py` | | `bind_all_handlers()` — the composition root |
| `apps/api/app/api/v1/agentic.py` | 292 | 6 HTTP routes |
| `apps/api/app/workers/agentic_tasks.py` | | `nur.agentic.dispatch`, `nur.agentic.recover`, execution task |
| `apps/api/app/workers/asyncrun.py` | | `run_task()` — disposes the engine in `finally` |
| `apps/api/app/models/agentic.py` | | 9 tables |
| `apps/api/app/tests/agentic/` | | 471 tests |
| `docs/agentic/AGENCY_PLANE_BUILD_PLAN.md` | | the plan |

### Tables (migrations 0035–0049)

`agent_workflows`, `agent_steps`, `agent_approvals`, `agent_run_events`,
`agent_checkpoints`, `agent_tool_calls`, `agent_policies`, `agent_evaluations`,
`agent_dispatch_outbox`.

### The four production-dead defects this subsystem was built to fix

Each was invisible to a green suite because every test supplied in-process what
production never did. **This is the pattern to watch for.**

| # | defect | why the suite missed it |
|---|---|---|
| 1 | No agentic Celery task was registered — `celery_app.include` listed only `app.workers.tasks`, so a real worker knew none of `nur.agentic.*` | tests import `agentic_tasks` directly, which registers as a side effect |
| 2 | No tool handler was ever bound in production — a real worker raised `UnboundToolError` for every tool | every test bound handlers itself in a fixture |
| 3 | Every `asyncio.run` task died on its **second** invocation ("Event loop is closed") — the loop closes while the engine is a process singleton | each task was only ever called once per process |
| 4 | Dispatch and recovery swept **zero rows** — both run with no `app.current_user_id`, and `nur_app` correctly has no BYPASSRLS, so under FORCE RLS both were blind | tests set an owner context, so the sweep always had a scope |

Also fixed: no production dispatcher existed; the claim shared a transaction with
the handler (a killed worker rolled back its own claim); `MAX(sequence)+1` let a
concurrent ledger append abort its own transaction; `cost_cents` was never written;
quiet hours were never loaded; an unknown timezone crashed `load_policy`; the
timeout path crashed recording its own failure; `apply_edit` had seven tests and no
production caller.

### Migration 0047 — the cross-owner boundary

`BYPASSRLS` on `nur_app` would expose every owner's data to the request-serving
role. Instead: four narrow `SECURITY DEFINER` functions with pinned `search_path`,
`REVOKE ALL FROM PUBLIC` then `GRANT EXECUTE` to `nur_app` alone —
`agent_ops_claim_dispatch`, `agent_ops_mark_dispatch_sent`,
`agent_ops_mark_dispatch_failed`, `agent_ops_reclaim_expired_steps`. `nur_app`
gains **no table privilege**. Pinned by `test_ops_boundary_db.py` (10 tests),
including that no function body references an owner-content table.

### Durable claim (0046)

Two transactions: the claim commits alone, then everything is reloaded under it.
`execution_attempt` is reissued on every claim and reclaim, and every completion,
failure, timeout and terminal transition is fenced on it — `worker_id` alone would
still match a reclaimed worker's own name. No heartbeat: a hard `asyncio.wait_for`
ceiling (120s) is capped strictly below the lease (300s), proven by
`test_the_ceiling_is_always_below_the_lease`.

---

## 4. Subsystem 2 — Orbit (people and relational gravity)

Route `/universe/orbits`.

| path | lines | role |
|---|---|---|
| `apps/api/alembic/versions/0050_orbit_relational_world.py` | | 8 tables + 14 `people` columns |
| `apps/api/app/models/orbit_relational.py` | | ORM + shared vocabularies |
| `apps/api/app/api/v1/orbit_world.py` | 937 | 23 routes |
| `apps/api/app/tests/test_orbit_world.py` | | 30 tests |
| `apps/web/src/bridge/v197Orbit.ts` | 1,314 | the surface |
| `apps/web/src/styles/v197-orbit.css` | 864 | |
| `apps/web/e2e/orbit-surface.spec.ts` | | 11 tests |

Tables: `orbit_groups`, `orbit_group_members`, `orbit_relationships`,
`orbit_context_links`, `orbit_layout_nodes`, `orbit_threads`,
`orbit_relational_insights`, `orbit_relational_signals`.

### Schema-enforced guarantees

- `orbit_relational_signals.basis` ∈ {`USER_STATED`, `OBSERVED`, `NUR_INFERRED`}.
  A `NUR_INFERRED` row with an empty evidence array is **rejected**.
- `contradictory_evidence` sits on the same row as `evidence`, so the case against a
  reading is as durable as the case for it.
- `orbit_relational_insights.may_be_wrong_about` is NOT NULL, non-blank CHECK, no
  default — an insight that cannot state its own doubt cannot be stored.
- `people.inference_allowed` is checked before any inferred signal is written (403).

**Deliberate deviation:** spec §27 suggested an `orbit_entities` table. That would
duplicate `people`, already referenced by `orbit_members`,
`orbits.primary_person_id`, `timeline_events.person_id`, Capsules and consultations.
`people` gained columns instead.

**Not built:** Add Person / Create Group use `window.prompt` rather than the
multi-step drawers; no group detail tabs, bulk actions, relationship-type filters,
Group NUR workspace, or RTL verification.

**Honestly disabled** (reason in tooltip): Open Talk, Add Context, Start Plan,
Import from NUR context, Open Group NUR, Plans tab.

---

## 5. Subsystem 3 — Map (systems, paths, possible futures)

Route `/universe/map`.

| path | lines | role |
|---|---|---|
| `apps/api/alembic/versions/0051_map_compositional_layer.py` | | 7 tables + `predictions` extended |
| `apps/api/app/models/map_layer.py` | | ORM + vocabularies (`REF_TYPES`, `EDGE_TYPES`, …) |
| `apps/api/app/api/v1/map.py` | (modified) | 7 routes — the composed graph, extended here |
| `apps/api/app/api/v1/map_workspace.py` | 1,898 | 30 routes |
| `apps/api/app/tests/test_map_workspace.py` | | 39 tests |
| `apps/web/src/bridge/v197Map.ts` | 1,924 | the surface |
| `apps/web/src/styles/v197-map.css` | 926 | |
| `apps/web/e2e/map-surface.spec.ts` | | 19 tests |

Tables: `map_views`, `map_layouts`, `map_edges`, `map_suggestions`,
`map_annotations`, `map_decision_options`, `map_blockers`.

### Reuse decision (important — do not undo)

`/api/v1/map` **already existed** and already composed most of the graph. Canonical
`goals`, `objectives`, `plans`, `plan_steps`, `decisions`, `outcomes`,
`predictions`, `system_actions`, `timeline_events`, `people`, `research_*` all
already existed. Map adds **no duplicate**. Two additions are genuinely new:

- `map_decision_options` — a `decisions` row has statement/rationale/status and **no
  options**, so there was nothing to compare and no way to record which fork was
  taken.
- `map_blockers` — a "blocker" was any `system_actions` row with status `MISSED`, or
  a bare string in `system_diagnostics.blockers`. Neither could say what it affects,
  what evidence it rests on, whether the owner agrees, or how it was resolved.

`predictions` was **extended in place** (assumptions, confidence, horizon_days,
review_by, resolution, learning) — the same call as `people` for Orbit.

### Schema-enforced guarantees (all falsified against live Postgres)

- `ck_predictions_never_certain` — `confidence` strictly between 0 and 1. **A
  prediction cannot be stored as certainty.**
- `ck_map_edge_inference_needs_source` — an unconfirmed edge must name what it was
  inferred from; and unconfirmed edges are returned in `suggested_changes`, never in
  `edges`.
- `ck_map_suggestion_has_explanation` / `ck_map_suggestion_states_doubt` — both
  NOT NULL and refused blank, so the "Why?" action always has substance.
- `ck_map_blocker_sensitive_needs_owner` — an inferred `EMOTIONAL` /
  `PSYCHOLOGICAL` / `RELATIONAL` blocker **cannot reach `OPEN`**; it waits at
  `PROPOSED` until `confirmed_by_owner`. §20 is unreachable-by-construction, not
  merely discouraged.
- `uq_map_decision_one_choice` — one chosen option per decision.
- `ck_map_view_focus_needs_root` — a FOCUS view without a root is refused.

### Deterministic, not intelligent

There is **no model provider anywhere in this repository**. `/map/problem`,
`/map/path-comparison` and `/map/decision-analysis` label themselves
`DETERMINISTIC_FRAME` with `is_model_generated: false`. Suggestions are pattern
matches over real rows (duplicate plan titles, deadlines within 7 days, predictions
past `review_by`, a System with goals but no outcomes), each naming its source rows.
A recommendation appears **only** when the caller states a priority, returned as
`governing_assumption`.

**Not built:** pan/zoom (so Fit-all is disabled); Add Goal / Add Signal / Map a
Problem / Add Decision drawers (endpoints live and tested); Connect-mode gesture;
Glow wiring from Map. Drag-to-reposition **is** built (pointer + arrow keys through
one `moveTo` path).

---

## 6. Subsystem 4 — Timeline (the temporal layer)

Route `/universe/timeline`.

| path | lines | role |
|---|---|---|
| `apps/api/alembic/versions/0052_timeline_temporal_layer.py` | | 6 tables + `timeline_events` extended |
| `apps/api/app/models/timeline_layer.py` | | ORM + vocabularies |
| `apps/api/app/api/v1/timeline.py` | (modified) | 11 routes — creation now accepts truth fields |
| `apps/api/app/api/v1/timeline_workspace.py` | 1,490 | 32 routes |
| `apps/api/app/tests/test_timeline_workspace.py` | | 27 tests |
| `apps/web/src/bridge/v197Timeline.ts` | 1,270 | the surface |
| `apps/web/src/styles/v197-timeline.css` | 961 | |
| `apps/web/e2e/timeline-surface.spec.ts` | | 18 tests |

Tables: `timeline_phases`, `timeline_recurrences`, `timeline_reschedules`,
`timeline_reviews`, `timeline_external_links`, `timeline_preferences`.

### Reuse decisions (do not undo)

- `timeline_events` (`app/models/intelligence.py`) and `scheduled_actions`
  (`app/models/living.py`) **already were** the Event / Action / Time-Block object
  model. The composed views read **both**. `scheduled_actions` mutation stays on
  Living's own route (`PATCH /api/v1/schedules/{id}`) — Timeline composes it for
  reading and does not shadow its write path.
- **Dependencies reuse `map_edges` from 0051.** No `timeline_dependencies` table
  exists. `map_edges` already had `DEPENDS_ON`, `timeline_event` in its ref-type
  vocabulary, and `user_confirmed`. The dependency flavour and lag live in
  `edge_metadata` (schemaless JSONB), so the reuse cost **no migration to 0051**.
- `timeline_events` extended in place: `ends_at`, `all_day`, `timezone_name`,
  `date_precision`, `earliest_at`, `latest_at`, `actual_start_at`, `actual_end_at`,
  `completion_state`, `phase_id`, `visibility_scope`, `energy_type`.

### Schema-enforced guarantees (all falsified live)

- `ck_timeline_event_unscheduled_has_no_date` — an `UNSCHEDULED` entry cannot carry
  `scheduled_for`, `ends_at`, `earliest_at` or `latest_at`.
- `ck_timeline_event_completion_needs_actual` — a completion verdict requires
  `actual_end_at`.
- `ck_timeline_recurrence_flexible_needs_target` — a `FLEXIBLE` rhythm needs a
  `target_frequency`, so "three times a week, not fixed days" is measured against a
  count.
- `ck_timeline_phase_span`, `ck_timeline_review_period` — spans cannot run backwards.

### No silent conversions

§5's rule — never turn planned into completed, predicted into actual, inferred into
fact, imported into approved memory — is enforced by having **no generic status
PATCH anywhere**. Every transition is a named endpoint: `/schedule`, `/start`,
`/complete`, `/partial`, `/confirm-observed`, `/archive`.
`test_there_is_no_generic_status_patch_route` asserts the absence.

### Ripple: preview then confirm

`POST /timeline/ripple-preview` **persists nothing**. Only
`POST /timeline/ripple-apply` with an owner-chosen mode (`MOVE_ONLY`,
`SHIFT_DEPENDENTS`, `COMPRESS_LATER`, `KEEP_AND_FLAG`) writes, and it records a
`timeline_reschedules` row for every entry it touches. The drag gesture and the
keyboard path (`ArrowUp`/`ArrowDown`, and the Time tab's Reschedule control) open
the **same** dialog, so neither can drift from the other's guarantee.

### Honest about what it is not

- `/reviews/generate`, `/conflict-analysis`, ripple preview →
  `DETERMINISTIC_FRAME`, no model consulted.
- `/external-sync` → **503 with a reason**. No calendar provider is connected and it
  will not report a fake success.
- Workload → `UNKNOWN` per day. No capacity input is stored anywhere; §21 forbids
  inventing a score.

**Not built:** the Add flow, Ask-NUR-to-Schedule, Open-on-Map (disabled with reason
in tooltip); the Activity tab is a stated placeholder; Calendar is a grouped agenda,
not a pixel grid; no timezone-change prompt, no scenario strands, no Glow wiring;
mobile is Flow-only rather than the three-mode switcher.

---

## 7. The surface host (read before touching any surface CSS)

`apps/web/src/bridge/v197SurfaceHost.ts` (106 lines) — `claimV197SurfaceHost(doc)`
and `releaseV197SurfaceHost(doc)`.

Two earlier attempts were wrong and the module documents both:

1. **Opaque overlay.** Each surface used `position: fixed; inset: 0; z-index: 320`
   with `background: #000000`. That covered `#space3d` (280) and **NUR lost its
   stars**. The CSS comments called it deliberate, which made a bad decision look
   reasoned.
2. **Translucent overlay.** Stars returned — and so did the canonical page, because
   `#nur-front-v61` is at z-index 10 *below* the galaxy. Two interfaces at once.

The fix: mount into `SECTION.nur-viewport`, hide only `.nur-viewport > .nur-page`,
and leave the rail, topbar and `#space3d` completely alone. Surfaces now carry
**`position: relative`, `z-index: auto`, `background: transparent`**.

`claimV197SurfaceHost` returns `null` when the canonical viewport is absent, and
each surface then **declines to render** — falling back to `document.body` would
silently recreate the overlay. Every surface calls `releaseV197SurfaceHost` on its
non-matching route branch.

Also handled here: `#nur-a11y-live` is a direct child of `<body>` and was painting
its latest screen-reader announcement as loose text across every surface. It is
**clipped** (visually-hidden pattern), not hidden — `visibility: hidden` and
`display: none` both remove a live region from the accessibility tree.

Wiring point: `apps/web/src/bridge/v197Bridge.ts` `applyCurrentRoute()`, after the
adjunct call:

```ts
const orbitRendered = await renderV197Orbit(this.universeDocument, route, this.api);
if (orbitRendered) return;
const mapRendered = await renderV197Map(this.universeDocument, route, this.api);
if (mapRendered) return;
const timelineRendered = await renderV197Timeline(this.universeDocument, route, this.api);
if (timelineRendered) return;
```

---

## 8. Product boundaries (founder-locked, keep them distinct)

| surface | owns |
|---|---|
| **Today** | the immediate daily operating surface |
| **Orbit** | people, groups, relational gravity |
| **Map** | systems, goals, paths, dependencies, possible futures |
| **Timeline** | chronology, scheduling, history, horizons, temporal review |
| **Insights** | interpreted patterns across the evidence |

Cross-links are allowed; duplication is not. Map shows people as compact Orbit
sigils and links out; Timeline places Map objects in time without duplicating Map's
causal structure.

---

## 9. Open decision — CONFLICT-010 (blocking)

Recorded in `docs/conflict-and-supersession-report.md`.

The Map spec **and** the Timeline spec both name **seven** Systems: Quiet Ambition,
Rebuild, Study, Money, Body, Connection, Creation.

`apps/api/app/living/catalog.py` says *"Founder-locked definitions for NUR's **six**
Star Systems"* and holds: `ambition`, `rebuild`, `creation`, `growth`,
`introspection`, `connection`. `app/services/auth_service.py` `CORE_SYSTEMS` agrees
exactly and **seeds one Orbit per System at registration**.

The lists overlap on four concepts. Study, Money and Body do not exist anywhere in
the repository; `growth` and `introspection` are absent from the specs.

Changing this requires:
1. a data migration for every existing owner's `system_slug` rows — carried on
   `goals`, `system_actions`, `scheduled_actions`, `system_diagnostics`,
   `feasibility_assessments`;
2. six founder-authored `SystemDefinition` blocks (definition, 6–7 questions,
   checklist, `ignored_prediction`, `followed_prediction`) — founder voice, not
   inventable by an implementer;
3. contradicting the word "Founder-locked" in the file.

**Mitigation already in place:** Map's System regions and Timeline's System lane
grouping are **driven from the catalog**, never a hardcoded list, so both pick up a
seventh automatically the moment it is added.

**Consequence to state plainly:** Map acceptance criterion 1 ("Seven Systems appear
as meaningful regions") renders **six** today.

Also noted: `_stable_layout` in `app/api/v1/map.py` distributes System nodes with
`2 * math.pi / 7` while the catalog holds six, leaving a one-seventh gap — evidence
seven was once intended.

---

## 10. How to run and verify

```bash
# Bring the whole stack up (idempotent; re-syncs ports and DSNs, runs migrations,
# seeds demo data, and exits non-zero if the API or web smoke fails)
cd /home/nur/.cache/nur-full-completion-20260726
bash RUN_NUR.sh

# Demo credentials it prints
#   owner@nur.app / owner-demo-pass-123
#   recipient@nur.app / recipient-demo-pass-123
# Owner app: http://localhost:5173   API: http://localhost:8000

# API gates
cd apps/api && export PATH="$PWD/.venv/bin:$PATH"
python -m ruff check app
python -m pytest app/tests -q                 # 759 expected

# Migration round-trip and the released-upgrade path
python -m pytest app/tests/agentic/test_migration_roundtrip_db.py \
                app/tests/agentic/test_upgrade_from_released_db.py -q

# Web gates
cd ../web
npx tsc --noEmit
npm test          # 87
npm run build

# V197 integrity and secrets
cd ../.. && bash infra/scripts/check-v197-integrity.sh
bash infra/scripts/secret-scan.sh

# Playwright — kill any stale preview first, it will serve an old bundle
fuser -k 4173/tcp; cd apps/web
npx playwright test e2e/timeline-surface.spec.ts e2e/map-surface.spec.ts \
  e2e/orbit-surface.spec.ts e2e/v197-star-brain.spec.ts \
  e2e/v197-runtime-lifecycle.spec.ts --project=chromium-desktop
# projects: chromium-desktop, chromium-mobile, webkit-mobile
```

Screenshots (gitignored by repo convention — `proof/**/*.png`, run evidence
regenerates and is meaningless once the SHA moves):
`proof/screenshots/{timeline,stars,map}/`.

---

## 11. Traps that already cost real time

Read these. Each one is a real defect that shipped into this repository and was
found the hard way.

### 11.1 Never give a surface `position: fixed` or a background

`#space3d` (z-index 280, `mix-blend-mode: screen`) is the starfield. A surface above
it with an opaque background **erases the galaxy**. A surface above it with a
translucent background lets the canonical page bleed through. Mount inside the
shell via `v197SurfaceHost` and carry no background at all. See §7.

### 11.2 The RLS context is transaction-local

`set_config('app.current_user_id', …, true)` is **transaction-local**. Committing
drops it. Consequences seen in production code:

- The Agency Plane's split claim transaction lost its context, so every owner-scoped
  read after the commit returned nothing. Fix: `await set_user_context(db, owner_user_id)`
  after the claim commit.
- `generate_suggestions` in `map_workspace.py` committed and then re-read, and the
  response reported `created: 1` beside an **empty list**. Fix: `flush()`, read,
  build the response, *then* `commit()`.

**Rule: never read owner-scoped rows after a commit in the same request.**

### 11.3 An unnamed inline CHECK is not replaced by adding another

`0015_live_intelligence.py` created `timeline_events.status` with an inline
`CHECK (status IN (...5 values...))`. Postgres auto-named it
`timeline_events_status_check`. Adding a wider CHECK in `0052` did **not** replace
it — both applied, ANDed — so every new truth state was still rejected while the
migration appeared to allow it. `0052` drops the old constraint first and restores
it on downgrade.

**Rule: before widening a column's vocabulary, grep every prior migration for an
inline CHECK on that column.**

### 11.4 Never edit a released migration in place

I edited `0043` in place; a database already stamped past it never received the
columns, and a live instance raised `column agent_approvals.invalidated_from does not
exist`. Fixed forward in `0049_consent_provenance_backfill.py`, with
`test_upgrade_from_released_db.py` walking the real deployment upgrade path and
reproducing the failure verbatim when `0049` is removed.

### 11.5 asyncpg specifics

- One command per prepared statement — **DDL must be split**. Migrations 0050–0052
  use a `_statements()` splitter that strips `--` comments first, because a
  semicolon inside a comment cut a `CREATE TABLE` in half.
- A reused NULL parameter needs an explicit cast: `CAST(:attempt AS uuid)`.

### 11.6 `nur_admin` needs BYPASSRLS or migration DML silently no-ops

Provisioned in `infra/scripts/bootstrap-dev.sh` and `app/tests/conftest.py`
(`ALTER ROLE nur_admin BYPASSRLS`) — **not** in a migration, since only a superuser
can grant it. Without it, every migration-time `UPDATE`/`INSERT` is a silent no-op.

### 11.7 SQLAlchemy defaults are applied at flush, not construction

`TimelinePreference(owner_user_id=…)` read back `view_mode == None`, not `"FLOW"`.
A transient un-flushed row does not carry `mapped_column(default=...)`. The GET
route states the defaults directly rather than writing a row on a read.

### 11.8 Playwright, in this repo specifically

- **Serial mode, one shared signed-in page.** A context per test means one sign-in
  each and the auth limiter correctly starts returning 429 partway through the file —
  the suite then tests the limiter, not the surface.
- **Resolve the frame from the element handle**, not `frames()[0]` — the entry stage
  is also a direct child of the main frame and holds no surface.
- **Kill stale `vite preview` on 4173** or it serves an old bundle and you debug a
  build that no longer exists.
- **Wait for data, not the first paint.** Every surface exposes
  `data-{map,timeline}-loaded`; poll it. Asserting against the initial empty render
  passed on desktop Chromium and failed on WebKit mobile.
- **Scroll into view before a pointer gesture.** A drag at coordinates outside the
  viewport lands on nothing.
- **Make a test seed its own preconditions.** The Orbit basis test passed for a while
  on residual database state and failed the first time it met a freshly seeded
  environment.
- A test that mutates persistent state must **reset** first — the Map drag test
  drifted its node further off-canvas every run until the press missed.
- The Orbit signals endpoint is **`PUT`** (an upsert keyed on person+kind+basis), not
  `POST`. A `POST` silently 405s.

### 11.9 `#nur-a11y-live` is outside the chrome

It is a direct child of `<body>`. Hiding `#nur-front-v61` does not cover it. Clip it,
never hide it — hiding removes a live region from the accessibility tree.

### 11.10 CORS `allow_methods` is explicit

`apps/api/app/main.py` lists methods. `PUT` was missing and Map's layout write would
have failed preflight cross-origin — dragging would have silently never persisted.
Current list: `GET, POST, PUT, PATCH, DELETE, OPTIONS`.

---

## 12. Standing constraints (founder, still in force)

- Do **not** request an OpenAI credential; never ask the founder to paste keys into
  chat; never hardcode keys; no secrets in logs, screenshots, evidence or git.
- Do **not** touch or redesign canonical V197.
- Do **not** build a parallel React interface.
- Do **not** work on the planner.
- Do **not** force-push. Do **not** merge to main. PR #11 stays draft.
- Do **not** delete evidence or historical rows.
- Do **not** hide defects by weakening tests.
- Do **not** claim DONE from static inspection, grep, AST tests or local test counts
  alone — run it.
- Founder ruling on other worktrees: *"DONT MAKE THEM CANON JO MISSING HAI WOH HI LE
  ISSE"* — do not crown another worktree; take only what is genuinely missing.
- Founder ruling on the shell: the **checkpoint UI stays**; Map, Orbit and Timeline
  live **inside** it.

---

## 13. Suggested next steps, in priority order

1. **Resolve CONFLICT-010** (founder decision, §9). Everything about the seven
   Systems is blocked on it. Nothing else in the repository is.
2. **Run the mobile and WebKit Playwright projects at head.** Map has been verified
   on all three projects at an earlier SHA (`8fb8086`); Timeline and the hosting
   change have only been verified on `chromium-desktop` at `2f3d8b5`. One command,
   §10.
3. **The disabled drawers.** Highest product value per unit of work, because every
   endpoint behind them is already live and tested:
   - Map: Add Goal, Add Signal, Map-a-Problem (`POST /map/problem`), decision
     choosing (`POST /map/decisions/{id}/choose/{option}`).
   - Timeline: the Add flow (`POST /timeline/events`), natural-language date entry
     with a structured confirmation.
   - Orbit: Add Person / Create Group drawers, replacing `window.prompt`.
4. **Pan/zoom for Map**, which also un-disables Fit-all.
5. **Timeline's Activity tab**, currently a stated placeholder — compose
   `timeline_reschedules` + the canonical event ledger into one feed.
6. **Insights** is the one specified surface not yet built.
7. **Provider-backed execution** remains unproven by design. A test fails if
   `openai`, `Runner.run` or `responses.create` appears in the agentic runtime.
   `docs/conflict-and-supersession-report.md` notes SOL 5.6 §28.4 arrived truncated,
   so no §28 verdict can be claimed until the founder resends the tail.

---

## 14. Where the truth lives

- **Conflicts and supersessions:** `docs/conflict-and-supersession-report.md`
  (CONFLICT-001 … CONFLICT-010).
- **Agency Plane plan:** `docs/agentic/AGENCY_PLANE_BUILD_PLAN.md`.
- **This document:** `docs/CODEX_HANDOFF.md`.
- **Run evidence:** `proof/` (gitignored; regenerate on demand).
- **PR narrative:** `am-selenephos/NUR#11` body — kept current with each head.
