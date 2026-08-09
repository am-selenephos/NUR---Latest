# Agency Plane — build plan and handoff

Historical handoff from branch `claude/nur-agentic-spine-20260728`, draft PR #11,
base `codex/nur-full-completion-20260726`.

## Current reconciliation at `7df3ade`

This phase table is a PR #11 authoring snapshot, not current completion evidence. The current
baseline contains a typed Agency tool registry, compiler, policy engine, exact-call approval
records, dispatch outbox, runtime, worker tasks, and a Mind-to-Agency proposal bridge. The public
API exposes tool/workflow/event/approval reads and approval decisions. Direct owner lifecycle
create/start/cancel/retry routes and the V197 owner Agent surface remain incomplete. These facts
do not establish end-to-end Agency release readiness.

Written to be executed, not admired. Every remaining phase names the files it
touches, the guarantee it must prove, and the test that proves it. Where I hit a
trap, it is recorded here rather than left for the next person to rediscover —
several cost an hour each.

## Where the line is

| # | Phase | State | SHA |
|---|-------|-------|-----|
| 1 | Workflow/step state machine | **done** | `8fb101b` |
| 2 | Durable schema + forced RLS | **done** | `60d298d` |
| — | Migration targeting fix | **done** | `8fb187e` |
| 3 | Append-only events + checkpoints | **done** | `38cce51` |
| 4 | Recovery, leases, idempotency | **done** | `38cce51` |
| 5 | Risk / capability / policy engine | **done** | `33c139a` |
| 6 | Typed tool registry | next | — |
| 7 | Planner, compiler, verifier | — | — |
| 8 | Approval, checkpoint, resume | — | — |
| 9 | Celery orchestration + OTel | — | — |
| 10 | V197 Agency drawer / inbox / run detail | — | — |
| 11 | Personal Movement workflow | — | — |
| 12 | Research-to-Decision workflow | — | — |
| 13 | Project Delivery workflow | — | — |
| 14 | Evaluations, adversarial tests, CI | — | — |

36 agentic tests, 228 across the API suite.

## Traps already paid for

**Alembic used to migrate the wrong database and report success.** `env.py`
fell back to a hardcoded `localhost:5432`, which is not this project's database
— the container publishes 15432. Running alembic from a plain shell created
every table somewhere the app never reads and printed a clean upgrade. Fixed in
`8fb187e`: an unset environment is now a hard error. **Always export
`ALEMBIC_DATABASE_URL`** (the schema-owner role; `nur_app` cannot write
`alembic_version`).

**`config.py` still defaults `database_url` to `localhost:5432`.** Same trap one
layer down, not yet closed. Worth fixing when the settings module is next
touched.

**asyncpg prepares every statement and a prepared statement holds one command.**
A multi-statement DDL block raises `cannot insert multiple commands into a
prepared statement`. Keep the DDL as one readable document and split on `;` at
execution — see `0035_agentic_spine.py`.

**`nur_admin` needs `GRANT nur_email_lookup TO nur_admin`** or migration 0034
fails against a fresh container. `infra/scripts/provision-email-lookup-role.sh`
exists for this.

**The V197 entry stage takes ~8 seconds to become interactive.** Anything
shorter reads an empty frame and produces confident, wrong measurements.

**Duplicate element IDs exist in the entry stage.** `getElementById` and
`.first()` return a hidden 0×0 copy; filter for visible elements or submit forms
directly.

## Phase 6 — typed tool registry

`apps/api/app/agentic/tools.py`, `registry.py`.

Each tool is a `ToolContract` (already defined in `policy.py`) plus a handler.
The registry is the join between abstract risk classes and real NUR
capabilities.

Ship read-only first, because they are provable without any mutation:

```
R0  get_today_state · get_system_snapshot · get_plan · get_timeline
    get_map_neighbourhood · get_orbit · get_project · get_project_evidence
    get_insight · search_approved_memory · get_omega_workspace_frame
R1  create_draft_plan · create_research_brief · create_memory_candidate
    create_project_task_draft · create_timeline_draft
    create_insight_candidate · save_private_artifact
R2  activate_plan · schedule_timeline_event · complete_task
    accept_or_correct_insight · create_capsule · queue_project_run
```

Do **not** ship shell, filesystem, network, repository write, messaging,
publish, deploy, payments or secret access. The catalog already denies these;
keep it that way.

Reuse the existing services rather than re-querying. `get_map_neighbourhood`
should call the same assembly `/api/v1/map` uses — a second implementation will
drift from the first and the drift will be invisible.

Must prove:
- every registered tool has a contract and a handler (no orphans in either direction)
- no R0 handler performs a write — assert against the SQL it issues, not by reading it
- `search_approved_memory` returns only `OWNER_WRITTEN`/approved rows, never candidates
- unknown tool key raises rather than returning empty

## Phase 7 — planner, compiler, verifier

`planner.py`, `compiler.py`, `verifier.py`.

The compiler turns a plan into `agent_steps` rows. Dependencies are step **keys**,
not ids — already the schema's shape, so re-planning does not rewrite references.

Must prove:
- a cyclic plan is rejected at compile time, not discovered at run time
- a step whose tool is denied by policy fails compilation with the policy reason
- the verifier is a *different* role from the executor; a step cannot verify itself
- `NEEDS_REVISION` re-plans at `plan_version + 1` and leaves the prior version intact

## Phase 8 — approval, checkpoint, resume

`approvals.py`, `checkpoints.py`.

`argument_digest` is already built and tested. The remaining work is the pause:
serialise resumable state into `agent_checkpoints`, and on resume recompute the
digest and compare.

Must prove:
- approving then mutating an argument invalidates the approval (digest mismatch → `INVALIDATED`)
- an expired approval cannot be redeemed
- resume executes the **exact** call that was approved, not a regenerated one
- a checkpoint with `redacted = false` is not resumable

## Phase 9 — Celery orchestration

`workers/agentic_tasks.py`.

Queue IDs only — never the graph. `claim_step` already makes duplicate delivery
safe; the task must call it and exit quietly when `claimed=False`.

Must prove:
- worker restart mid-run resumes from checkpoint
- `reclaim_expired_steps` returns an abandoned step and it completes once
- OTel trace id propagates API → queue → worker → tool call

## Phase 10 — V197 surfaces

`bridge/v197Agentic.ts`, `v197AgenticActions.ts`, `v197AgenticHydration.ts`.

Follow the lens pattern from `bridge/universe-lenses/` — canonical classes, a
real child element rather than a canonical pseudo-element, no second rAF.

The approval inbox must show what NUR wants to do, why, the exact arguments, the
scope, reversibility, cost ceiling, and Approve / Reject / Edit. An approval the
owner cannot fully read is not consent.

## Acceptance

`NUR_AGENTIC_SPINE_PASS` needs all of: restart survival, idempotent duplicate
delivery, stale-worker recovery, cancel/retry, exact-call approval resume,
argument mutation invalidating approval, forced RLS and cross-owner denial,
capability/scope/budget/timeout enforcement, honest provider failure, no silent
memory, no secrets in queues or traces, three flagship workflows end to end,
projections into Timeline/Map/Insight/Project, V197 showing work and failures,
and founder review of the real headed flow.

Anything less is `NUR_AGENTIC_PARTIAL`. An LLM calling one function is not a
pass.

## Still open outside this branch

- Galaxy invisible on the founder's screen — `?nur-diagnose=1` needs a run on their machine; five hypotheses falsified here
- Orbits / Timeline / Insights lens modules (PR #10 landed Map only)
- PRs #3 and #4 need triage — the only two with unique commits
- Frame rate 21–33 FPS against a ≥55 target
- A provider credential was reportedly pasted into a chat transcript. Treat it as exposed:
  revoke and rotate it immediately through the provider control plane, out of band. Never read,
  copy, transfer, provision, or reuse the old value to recover a prior proof.
