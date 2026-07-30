# NUR — continuation prompt

Hand this whole file to the next agent. It is written to be pasted as a prompt, not
skimmed as documentation. Everything needed to continue is here or pointed at
precisely.

---

## 0. Your task

You are continuing work on **NUR**, a personal-intelligence product, on branch
`claude/nur-agentic-spine-20260728` of `am-selenephos/NUR`, in the worktree
`/home/nur/.cache/nur-full-completion-20260726`.

Four subsystems are built and verified: the **Agency Plane**, **Orbit**, **Map** and
**Timeline**. Your job is to continue from head `861b7ef` — not to redesign, not to
re-audit, and not to rebuild what already exists and passes.

Work through §8 in order. Before writing any code, read §3 (constraints), §4
(architecture law) and §7 (traps). §7 is not optional; every item in it is a defect
that already shipped into this repository and cost real debugging time.

**Read `docs/CODEX_HANDOFF.md` alongside this file.** It carries the same facts with
more file-level detail.

---

## 1. Exact state

| field | value |
|---|---|
| Worktree | `/home/nur/.cache/nur-full-completion-20260726` |
| Branch | `claude/nur-agentic-spine-20260728` |
| Head | `861b7ef` — local == remote, clean tree |
| Base | `f024e6b951b3d603b39ecbb7fd6bf16d01d0a373` |
| Scope | 67 commits · 123 files · +36,600 / −26 · 18 migrations |
| Alembic head | `0052_timeline_temporal_layer` |
| PR | `am-selenephos/NUR#11` — **draft**, do not merge |
| CI | `.github/workflows/readiness.yml` — jobs `api` and `web-and-security` |
| Last green CI | run `30536464751` on `2f3d8b5`: both jobs success, Ruff + pytest executed |

### Verified at head — do not re-derive these

| gate | result |
|---|---|
| API suite | **759 passed**, 0 skipped |
| Ruff | clean |
| Web typecheck | clean |
| Web unit | 87 passed (18 files) |
| Web build | clean |
| `check-v197-integrity.sh` | `"pass": true` |
| `secret-scan.sh` | clean |
| Playwright chromium-desktop | **52 passed** — Timeline 18, Map 19, Orbit 11, star-brain 4, lifecycle |

CI provisions **both** `pgvector/pgvector:pg16` and `redis:7`. The real-broker E2E
runs and passes in CI (`test_real_broker_e2e_db.py ...`, three tests). Do not repeat
the earlier false claim that it is unenforced.

---

## 2. What NUR is, and the boundaries that must stay

NUR is one product with distinct surfaces. Keeping them distinct is a founder
requirement, repeated across specs. Do not let them collapse into four skins on one
dashboard.

| surface | owns | route |
|---|---|---|
| **Today** | the immediate daily operating surface | `/today` |
| **Orbit** | people, groups, relational gravity | `/universe/orbits` |
| **Map** | systems, goals, paths, dependencies, possible futures | `/universe/map` |
| **Timeline** | chronology, scheduling, history, horizons, temporal review | `/universe/timeline` |
| **Insights** | interpreted patterns across the evidence | `/universe/insights` — **not built** |

Cross-links are welcome. Duplication is not. Map shows people as compact Orbit
sigils and links out; Timeline places Map objects in time without duplicating Map's
causal structure.

---

## 3. Standing constraints (founder; still in force)

Absolute:

- Do **not** request an OpenAI or any provider credential. Never ask the founder to
  paste a key into chat. Never hardcode a key. No secrets in logs, screenshots,
  evidence, or git.
- Do **not** touch or redesign canonical V197. Its bytes are immutable.
- Do **not** build a parallel React interface. `#root` must be absent from every
  product page.
- Do **not** work on the planner.
- Do **not** force-push. Do **not** merge to main. PR #11 stays **draft**.
- Do **not** delete evidence or historical rows.
- Do **not** hide a defect by weakening a test.
- Do **not** claim DONE from static inspection, grep, AST tests or a local test count
  alone. Run the thing.

Founder rulings that have already been made — treat as settled:

- **The checkpoint UI stays.** The left rail, the top nav
  (UNIVERSE · MAP · ORBITS · TIMELINE · INSIGHTS), the starfield and the star-brain
  are NUR's identity. Surfaces render **inside** that shell, never over it.
- On other worktrees: *"DONT MAKE THEM CANON JO MISSING HAI WOH HI LE ISSE"* — do not
  crown another worktree as canonical; take only what is genuinely missing.

Working style the founder has asked for:

- Reuse first. Audit what exists before adding a table, a route or a store. Several
  earlier specs asked for tables that would have duplicated canonical ones; each was
  correctly refused and the canonical table extended instead.
- Enforce honesty rules in the **schema** where possible, not in a service that can
  be bypassed. Then falsify each constraint against live Postgres before building on
  it.
- Label anything deterministic as deterministic. There is no model provider in this
  repository; nothing may imply reasoning it did not do.
- Report failures plainly, with output. If something is skipped, say so.

---

## 4. Architecture law

Canonical V197 owns the visible product.

- Canonical document: `apps/web/public/v197/NUR_V197_CHECKBOX_TICK_RESTORED.html`.
  **Never edited.** `infra/scripts/check-v197-integrity.sh` hashes host, entry and
  universe and must return `"pass": true`.
- New surfaces are plain DOM/SVG adjuncts injected through
  `apps/web/src/bridge/v197Bridge.ts`.
- Spec component trees (Orbit §29, Map §38, Timeline §58) are preserved as **function
  decomposition**, not React components.

### The shell, and where surfaces mount

```
BODY.universe-edition
├── DIV#nur-front-v61.nur-interior            z-index 10
│   └── DIV.nur-shell
│       ├── ASIDE.nur-rail                    left rail   (never touched)
│       └── MAIN.nur-main
│           ├── HEADER.nur-topbar             the world nav
│           └── SECTION.nur-viewport          ← surfaces mount HERE
│               ├── SECTION#page-systems.nur-page.active   hidden while mounted
│               └── DIV#nur-surface-host                    created by v197SurfaceHost
└── CANVAS#space3d                            z-index 280, mix-blend-mode: screen
```

`#space3d` is the galaxy: z-index **280**, above the shell at **10**, blending with
`screen` — which only ever *lightens*. That is why the starfield paints over
canonical content, and why a surface hosted inside the shell inherits stars for free.

Mount and release with `apps/web/src/bridge/v197SurfaceHost.ts`:

```ts
const claimed = claimV197SurfaceHost(doc);   // returns null if no canonical viewport
if (claimed === null) { releaseV197SurfaceHost(doc); return false; }
// …and on the non-matching route branch:
releaseV197SurfaceHost(doc);
```

A surface root carries **`position: relative`, `z-index: auto`, `background:
transparent`** and nothing else. See §7.1 for why.

---

## 5. What exists (do not rebuild)

### 5.1 Agency Plane — migrations 0035–0049

`apps/api/app/agentic/` (4,790 lines, 18 modules) · `app/api/v1/agentic.py` (6
routes) · `app/workers/agentic_tasks.py`, `app/workers/asyncrun.py` ·
`app/models/agentic.py` (9 tables) · `app/tests/agentic/` (**471 tests**).

Tables: `agent_workflows`, `agent_steps`, `agent_approvals`, `agent_run_events`,
`agent_checkpoints`, `agent_tool_calls`, `agent_policies`, `agent_evaluations`,
`agent_dispatch_outbox`.

Key modules: `orchestrator.py` (state machine, claim, transition, event sequence),
`runtime.py` (split transaction, tool-version gate, policy gate, timeout ceiling),
`dispatcher.py` (drains the outbox through the SECURITY DEFINER boundary),
`aggregate.py` (the one place workflow status is derived), `policy.py` /
`policy_store.py` (spend ceilings, quiet hours in the owner's timezone),
`handlers.py` (`bind_all_handlers()` — the composition root).

Migration `0047` is the cross-owner boundary: four narrow `SECURITY DEFINER`
functions with pinned `search_path`, PUBLIC revoked, `EXECUTE` granted to `nur_app`
alone. `nur_app` gains **no table privilege**. `test_ops_boundary_db.py` pins it.

Durable claim (`0046`): two transactions, `execution_attempt` reissued on every claim
and reclaim, every terminal transition fenced on it. No heartbeat — a hard
`asyncio.wait_for` ceiling (120s) capped strictly below the lease (300s).

### 5.2 Orbit — migration 0050

`app/models/orbit_relational.py` · `app/api/v1/orbit_world.py` (937 lines, 23 routes)
· `app/tests/test_orbit_world.py` (30) · `apps/web/src/bridge/v197Orbit.ts` (1,314) ·
`apps/web/src/styles/v197-orbit.css` (864) · `apps/web/e2e/orbit-surface.spec.ts` (11).

8 tables + 14 `people` columns. Schema guarantees: `basis` ∈ {`USER_STATED`,
`OBSERVED`, `NUR_INFERRED`}; a `NUR_INFERRED` signal with empty evidence is rejected;
`contradictory_evidence` sits beside `evidence`; `may_be_wrong_about` is NOT NULL and
non-blank; `people.inference_allowed` gates inferred writes (403).

**Deliberate deviation:** spec §27 asked for `orbit_entities`. That would duplicate
`people`, already referenced by `orbit_members`, `orbits.primary_person_id`,
`timeline_events.person_id`, Capsules and consultations. `people` gained columns.

### 5.3 Map — migration 0051

`app/models/map_layer.py` · `app/api/v1/map_workspace.py` (1,898 lines, 30 routes) +
`app/api/v1/map.py` extended (7 routes, the composed graph) ·
`app/tests/test_map_workspace.py` (39) · `apps/web/src/bridge/v197Map.ts` (1,924) ·
`apps/web/src/styles/v197-map.css` (926) · `apps/web/e2e/map-surface.spec.ts` (19).

7 tables. **`/api/v1/map` already existed** and already composed most of the graph;
canonical `goals`, `objectives`, `plans`, `plan_steps`, `decisions`, `outcomes`,
`predictions`, `system_actions`, `timeline_events`, `people`, `research_*` all
already existed. Map duplicates **none** of them.

Genuinely new: `map_decision_options` (a `decisions` row has no options, so there was
nothing to compare) and `map_blockers` (a "blocker" was a `MISSED` action or a bare
string, unable to say what it affects or how it was resolved). `predictions` was
**extended in place**.

Guarantees: `ck_predictions_never_certain` (confidence strictly between 0 and 1 — a
prediction cannot be stored as certainty); `ck_map_edge_inference_needs_source` (and
unconfirmed edges are returned in `suggested_changes`, never in `edges`);
`ck_map_suggestion_has_explanation` / `_states_doubt`;
`ck_map_blocker_sensitive_needs_owner` (an inferred EMOTIONAL/PSYCHOLOGICAL/
RELATIONAL blocker **cannot reach `OPEN`** — §20 is unreachable-by-construction);
`uq_map_decision_one_choice`; `ck_map_view_focus_needs_root`.

`/map/problem`, `/map/path-comparison`, `/map/decision-analysis` are
`DETERMINISTIC_FRAME` with `is_model_generated: false`. Suggestions are pattern
matches over real rows, each naming its sources. A recommendation appears only when
the caller states a priority, returned as `governing_assumption`.

### 5.4 Timeline — migration 0052

`app/models/timeline_layer.py` · `app/api/v1/timeline_workspace.py` (1,490 lines, 32
routes) + `app/api/v1/timeline.py` extended (11 routes) ·
`app/tests/test_timeline_workspace.py` (27) ·
`apps/web/src/bridge/v197Timeline.ts` (1,270) ·
`apps/web/src/styles/v197-timeline.css` (961) ·
`apps/web/e2e/timeline-surface.spec.ts` (18).

6 tables. **Reuse decisions that must not be undone:**

- `timeline_events` (`app/models/intelligence.py`) and `scheduled_actions`
  (`app/models/living.py`) already *were* the Event / Action / Time-Block model. The
  composed views read **both**. `scheduled_actions` mutation stays on Living's route
  (`PATCH /api/v1/schedules/{id}`).
- **Dependencies reuse `map_edges` from 0051.** There is no `timeline_dependencies`
  table. `map_edges` already had `DEPENDS_ON`, `timeline_event` in its ref-type
  vocabulary, and `user_confirmed`. Flavour and lag live in `edge_metadata`
  (schemaless JSONB), so the reuse cost **no migration to 0051**.
- `timeline_events` extended in place with 12 columns.

Guarantees: `ck_timeline_event_unscheduled_has_no_date`;
`ck_timeline_event_completion_needs_actual`;
`ck_timeline_recurrence_flexible_needs_target`; `ck_timeline_phase_span`;
`ck_timeline_review_period`.

**No generic status PATCH exists.** Every truth-state transition is a named endpoint
(`/schedule`, `/start`, `/complete`, `/partial`, `/confirm-observed`, `/archive`);
`test_there_is_no_generic_status_patch_route` asserts the absence. This is how §5's
"never silently convert planned into completed, predicted into actual, inferred into
fact" is enforced.

Ripple is preview-then-confirm: `/ripple-preview` persists nothing; only
`/ripple-apply` with an owner-chosen mode writes, recording a `timeline_reschedules`
row per touched entry. The drag gesture and the keyboard path open the **same**
dialog.

`/external-sync` returns **503 with a reason** — no calendar provider is connected
and it will not fake success. Workload is `UNKNOWN` per day because no capacity input
is stored anywhere.

---

## 6. What is NOT built — precise inventory

Everything below is genuinely missing, not merely untidy. Where an endpoint already
exists, it is named, because the work is UI-only.

### 6.1 Insights — the one specified surface with no interface at all

- No `apps/web/src/bridge/v197Insights.ts`. Route `/universe/insights` falls through
  to the canonical world lens.
- Backend exists: `apps/api/app/api/v1/insights.py`, **9 routes**, plus the `insights`
  table (`app/models/intelligence.py`) and `omega_claims` (`app/models/omega.py`).
- `POST /api/v1/insights/{id}/add-to-timeline` already creates a
  `TimelineEvent(event_type="INSIGHT_REVIEW_DUE", status="DUE")`.

### 6.2 Orbit — 11 honestly-disabled controls

Add a person, Add first person, Create Group Orbit, Import from NUR context, Open
Group NUR, Accept, Keep as is, Archive, Why is NUR showing this? (in some states).

Also missing: the multi-step Add Person / 8-field Create Group drawers (currently
`window.prompt`); group detail tabs; bulk actions; relationship-type and intelligence
filters; the Group NUR workspace; RTL verification.

### 6.3 Map — 10 honestly-disabled controls, each with its reason in the tooltip

| control | reason as shown |
|---|---|
| Add Goal | Goals are created on the Systems page, which owns the full goal form |
| Add Signal | Signals arrive from Talk, Journal, Today, Research and Web Signals |
| Map a Problem | Not a guided flow yet — `POST /api/v1/map/problem` is live and tested |
| Add Decision | Decisions are created against an Orbit; Map adds their options |
| Fit all | No pan/zoom transform exists to fit to |
| Choose an option | `POST /map/decisions/{id}/choose/{option}` is live and tested |
| Run an experiment first | Experiments exist in the backend, not wired to decisions |
| Ask a consultation | Consultations are a separate surface |
| Continue Plan | Plan execution lives on the Plan page |
| Add to Timeline | `POST /timeline/from-goal` exists |

Also missing: pan/zoom; Connect-mode gesture for drawing an edge on the canvas
(`POST /map/edges` is live); Glow wiring from Map.

Built and working: drag-to-reposition (pointer + arrow keys through one `moveTo`
path), layout persistence, Current Position on the anchor, the label budget.

### 6.4 Timeline — 3 honestly-disabled controls

| control | reason as shown |
|---|---|
| Add | Not a guided flow yet — `POST /timeline/events` is live and tested |
| Ask NUR to Schedule | No model provider is connected in this deployment |
| Open on Map | Not an in-panel jump yet |

Also missing: the Activity tab is a **stated placeholder**; Calendar is a grouped
agenda rather than a pixel grid; no timezone-change prompt ("keep 9:00 AM local or
preserve the instant?"); no scenario strands; no Glow wiring; mobile is Flow-only
rather than the three-mode switcher (Flow / Calendar / Review).

### 6.5 Verification gaps

- Timeline and the shell-hosting change are verified on **chromium-desktop only** at
  head. Map was verified on all three Playwright projects at an earlier SHA
  (`8fb8086`). **Run `chromium-mobile` and `webkit-mobile` at head.**
- No RTL verification on any surface.

### 6.6 Deliberately unproven

Provider-backed execution. No provider call exists anywhere in the agentic runtime,
and a test fails if `openai`, `Runner.run` or `responses.create` appears there. This
is by founder constraint, not oversight.

`docs/conflict-and-supersession-report.md` records that SOL 5.6 §28.4 arrived
**truncated** mid-sentence, so no §28 verdict can be claimed until the founder
resends the tail.

---

## 7. Traps — read before writing code

Each is a real defect that shipped here.

**7.1 Never give a surface `position: fixed`, a z-index, or a background.**
All three surfaces originally used `position: fixed; inset: 0; z-index: 320` with
`background: #000000`. That covered `#space3d` (280) and **NUR lost its stars** — the
founder's report was exactly that. Making the root translucent brought the stars back
*and* the canonical page beneath it (`#nur-front-v61` is z-index 10, below the
galaxy), producing two interfaces at once. The fix is `v197SurfaceHost`: mount inside
`SECTION.nur-viewport`, hide only `.nur-viewport > .nur-page`, leave the rail, topbar
and `#space3d` alone.

**7.2 The RLS context is transaction-local.**
`set_config('app.current_user_id', …, true)` dies on commit. Two production bugs came
from this: the Agency Plane's split claim lost its context so every owner-scoped read
after the commit returned nothing (fixed with `set_user_context` after the claim
commit); and `generate_suggestions` committed then re-read, returning
`created: 1` beside an **empty list** (fixed with flush → read → build → commit).
**Never read owner-scoped rows after a commit in the same request.**

**7.3 An unnamed inline CHECK is not replaced by adding another.**
`0015_live_intelligence.py` created `timeline_events.status` with an inline
`CHECK (status IN (...5 values...))`, auto-named `timeline_events_status_check`.
Adding a wider CHECK in `0052` did not replace it — both applied, ANDed — so every
new truth state was still rejected while the migration appeared to allow it. `0052`
drops the old one first and restores it on downgrade. **Before widening a column's
vocabulary, grep every prior migration for an inline CHECK on it.**

**7.4 Never edit a released migration in place.**
`0043` was edited in place; a database already stamped past it never received the
columns and a live instance raised `column agent_approvals.invalidated_from does not
exist`. Fixed forward in `0049`, with `test_upgrade_from_released_db.py` walking the
real deployment path and reproducing the failure verbatim when `0049` is removed.

**7.5 asyncpg.** One command per prepared statement — **DDL must be split**.
Migrations 0050–0052 use a `_statements()` splitter that strips `--` comments first,
because a semicolon inside a comment cut a `CREATE TABLE` in half. A reused NULL
parameter needs an explicit cast: `CAST(:attempt AS uuid)`.

**7.6 `nur_admin` needs BYPASSRLS or migration DML silently no-ops.**
Granted in `infra/scripts/bootstrap-dev.sh` and `app/tests/conftest.py`, **not** in a
migration (only a superuser can grant it).

**7.7 SQLAlchemy applies defaults at flush, not construction.**
A transient `TimelinePreference(owner_user_id=…)` read back `view_mode == None`, not
`"FLOW"`. The GET route states defaults directly rather than writing a row on a read.

**7.8 Playwright, in this repo.**
Serial mode with one shared signed-in page — a context per test means one sign-in
each and the auth limiter correctly 429s partway through. Resolve the frame from the
element handle, never `frames()[0]` (the entry stage is also a child of the main
frame). Kill stale `vite preview` on 4173 or you debug an old bundle
(`fuser -k 4173/tcp`). Wait for data, not the first paint — poll
`data-{map,timeline}-loaded`. Scroll into view before a pointer gesture. Make a test
seed its own preconditions (the Orbit basis test passed on residual state then failed
against a fresh environment). A test that mutates persistent state must reset first.
The Orbit signals endpoint is **`PUT`** (an upsert), not `POST` — a `POST` silently
405s.

**7.9 `#nur-a11y-live` is a direct child of `<body>`.**
Hiding `#nur-front-v61` does not cover it; it was painting its latest announcement as
loose text across every surface. **Clip** it (visually-hidden pattern), never hide it
— `visibility: hidden` and `display: none` both remove a live region from the
accessibility tree.

**7.10 CORS `allow_methods` is explicit.** `apps/api/app/main.py`. `PUT` was missing
and Map's layout write would have failed preflight cross-origin — dragging would have
silently never persisted. Current: `GET, POST, PUT, PATCH, DELETE, OPTIONS`.

---

## 8. Your task list, in priority order

### Task 1 — Close the verification gap (do this first; it is one command)

Run the mobile and WebKit Playwright projects at head and fix whatever they surface:

```bash
cd apps/web && fuser -k 4173/tcp
npx playwright test e2e/timeline-surface.spec.ts e2e/map-surface.spec.ts \
  e2e/orbit-surface.spec.ts --project=chromium-mobile
npx playwright test e2e/timeline-surface.spec.ts e2e/map-surface.spec.ts \
  e2e/orbit-surface.spec.ts --project=webkit-mobile
```

Expect WebKit mobile to be genuinely slow: every state change repaints the whole
surface root, so a five-tab walk takes ~84s. `test.slow()` is the correct response
for a multi-step test; **do not** weaken an assertion to make it pass.

**Done when:** all three projects pass at head, or every remaining failure is
explained with its cause and reported.

### Task 2 — Build Insights

The only specified surface with no interface. Backend is ready: 9 routes in
`app/api/v1/insights.py`, the `insights` table, and `omega_claims`.

- Read the founder's Insights spec before starting. If you do not have it, **ask for
  it** rather than inventing the product.
- Follow the established pattern exactly: a bridge-native surface hosted through
  `claimV197SurfaceHost`, its own stylesheet, function decomposition rather than
  React, glass capsules only, no boxed controls.
- Reuse first. Insights interprets patterns *across* the other surfaces' evidence; it
  must not duplicate `map_*`, `timeline_*` or `orbit_*` rows.
- Every reading must state its basis and what it may be wrong about — the same rule
  Orbit and Map already enforce in the schema.

**Done when:** the surface renders inside the shell, reads only real owner rows, has
its own e2e spec, and the full suite plus `check-v197-integrity.sh` still pass.

### Task 3 — The disabled drawers (highest product value per unit of work)

Every endpoint behind these is already live and tested. This is UI-only.

1. **Timeline Add flow** — `POST /timeline/events` accepts `status`,
   `date_precision`, `earliest_at`, `latest_at`, `visibility_scope`, `energy_type`.
   Include natural-language date entry that shows a **structured confirmation** before
   saving; nothing is created from casual language without it.
2. **Map a Problem** — `POST /api/v1/map/problem` returns a `DETERMINISTIC_FRAME`
   decision with option rows. Build the six-step flow. Keep the label honest: it
   frames, it does not reason.
3. **Map decision choosing** — `POST /map/decisions/{id}/choose/{option}`. One chosen
   option per decision is already enforced by `uq_map_decision_one_choice`.
4. **Orbit Add Person / Create Group drawers**, replacing `window.prompt`.
5. **Map Add Goal / Add Signal** — reuse `POST /api/v1/goals`; do not create a
   parallel write path.

**Done when:** each control is enabled, drives the existing endpoint, and has an e2e
test. Any control still disabled keeps a truthful reason in its tooltip.

### Task 4 — Map pan/zoom

Also un-disables Fit all. Keep layout persistence working: drag writes through
`moveTo` → `PUT /map/views/{id}/layout`, and position must never change meaning
(`test_dragging_a_node_never_changes_its_system` guards this).

### Task 5 — Timeline gaps

- **Activity tab** — currently a stated placeholder. Compose `timeline_reschedules`
  with the canonical event ledger into one feed.
- **Timezone-change prompt** — "keep this at 9:00 AM local, or preserve the original
  instant?" `timeline_events.timezone_name` already exists.
- **Mobile three-mode switcher** (Flow / Calendar / Review); currently Flow-only.

### Task 6 — Glow wiring

Neither Map nor Timeline awards Glow. The rules are specified: reward verified
movement (a consequential completion, a milestone, an honest failed outcome logged, a
schedule corrected, a blocker removed, a review completed, a plan revised after
evidence). Never reward opening a page, endless rescheduling, or fake completions.
`app/services/glow_service.py` `award_glow_if_eligible` already exists and is
idempotent and source-gated.

---

## 9. Blocked on the founder — do not work around it

**CONFLICT-010**, recorded in full in `docs/conflict-and-supersession-report.md`.

The Map spec **and** the Timeline spec both name **seven** Systems: Quiet Ambition,
Rebuild, Study, Money, Body, Connection, Creation.

`apps/api/app/living/catalog.py` says *"Founder-locked definitions for NUR's **six**
Star Systems"* and holds `ambition`, `rebuild`, `creation`, `growth`,
`introspection`, `connection`. `app/services/auth_service.py` `CORE_SYSTEMS` agrees
exactly and **seeds one Orbit per System at registration**.

The lists overlap on four concepts. Study, Money and Body exist nowhere in the
repository; `growth` and `introspection` are absent from the specs.

Resolving it requires (a) a data migration for every existing owner's `system_slug`
rows — carried on `goals`, `system_actions`, `scheduled_actions`,
`system_diagnostics`, `feasibility_assessments`; (b) six founder-authored
`SystemDefinition` blocks with definition, 6–7 questions, checklist,
`ignored_prediction` and `followed_prediction` — founder voice, not inventable; and
(c) contradicting the word "Founder-locked".

**Do not invent the definitions and do not silently rewrite the catalog.** Both Map's
System regions and Timeline's System lane grouping already read from the catalog, so
they will pick up a seventh automatically the moment the founder adds it.

**State plainly in any report:** Map acceptance criterion 1 ("Seven Systems appear as
meaningful regions") renders **six** today.

---

## 10. How to run and verify

```bash
cd /home/nur/.cache/nur-full-completion-20260726
bash RUN_NUR.sh          # idempotent: re-syncs ports/DSNs, migrates, seeds, smoke-tests
#   owner@nur.app / owner-demo-pass-123
#   http://localhost:5173  ·  API http://localhost:8000

cd apps/api && export PATH="$PWD/.venv/bin:$PATH"
python -m ruff check app
python -m pytest app/tests -q                    # 759 expected
python -m pytest app/tests/agentic/test_migration_roundtrip_db.py \
                app/tests/agentic/test_upgrade_from_released_db.py -q

cd ../web
npx tsc --noEmit && npm test && npm run build
cd ../.. && bash infra/scripts/check-v197-integrity.sh && bash infra/scripts/secret-scan.sh

cd apps/web && fuser -k 4173/tcp
npx playwright test e2e/timeline-surface.spec.ts e2e/map-surface.spec.ts \
  e2e/orbit-surface.spec.ts e2e/v197-star-brain.spec.ts \
  e2e/v197-runtime-lifecycle.spec.ts --project=chromium-desktop
```

If Postgres is down: `docker start nur_postgres`. If the stack has drifted (ports,
DSNs, containers), `bash RUN_NUR.sh` reconciles it — that is what it is for.

Screenshots go to `proof/screenshots/…` and are **gitignored by repo convention**
(`proof/**/*.png`: run evidence regenerates and is meaningless once the SHA moves).

---

## 11. Definition of done, per change

1. The thing runs. Not "the tests pass" — the actual app, through the actual UI or the
   actual worker.
2. Full API suite green, Ruff clean, typecheck clean, web unit green, build clean.
3. `check-v197-integrity.sh` returns `"pass": true`.
4. `secret-scan.sh` clean.
5. New behaviour has a test that would **fail without the change**. Where you enforce
   an honesty rule in the schema, falsify it against live Postgres and say so.
6. Committed and pushed. Same-SHA CI green on the exact head, with the `api` job's
   Ruff and pytest steps confirmed **executed, not skipped**.
7. PR #11 body updated to match the head. Keep it draft.
8. Anything not built is listed with its reason. Any control left disabled carries a
   truthful reason in its tooltip.

## 12. How to report

State what you built, what you verified and how, what you found, and what you did not
do. Name failures with their output. If you make a claim about coverage, name the run
and the step. If you were wrong about something earlier, correct it plainly and move
on — one such correction is already recorded in `docs/CODEX_HANDOFF.md` §1 (I claimed
CI had no Redis container and that the real-broker E2E was unenforced; it has one and
the test runs there).

Do not report DONE from a grep, an AST check or a local count alone.
