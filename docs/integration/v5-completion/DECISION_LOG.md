# DECISION LOG — NUR V5 100% Completion

Every entry records a decision made while executing the v6 orchestrator, with the
evidence behind it. Decisions are appended, never rewritten.

---

## D-001 — Environment gate PASS

`whoami=nur`, `HOME=/home/nur`, `/home/nur/Downloads` readable,
`/home/nur/NUR-INTEGRATION-20260722` is a real Git repository whose toplevel resolves to
itself. `hostname` is not installed on this Arch system; `uname -n` returned `archlinux`.
A missing optional binary is not an environment failure, so
`WRONG_EXECUTION_ENVIRONMENT` was **not** emitted.

## D-002 — Read the full binding corpus before touching code

All four documents were read completely, not summarised from memory:
`NUR_V5_MASTERPACK_MANIFEST_20260713.json` (55 lines),
`NUR_EXACT_STATUS_LEDGER_V5_20260713.md` (434),
`CODEX_NUR_COMPLETION_ORCHESTRATOR_V5_20260713.md` (718),
`NUR_LIVING_INTELLIGENCE_MASTERPLAN_V5_20260713.md` (3,887).

## D-003 — Work on a dedicated branch, not on the release candidate branch

Created `completion/nur-v5-full-pass` from `release/nur-p0-candidate` @ `6d7eeef`.
Not branched from public `main` (`f265123`), which is stale relative to the integration work.
No reset, no clean, no discard: the three untracked directories (`audit-output/`,
`proof/100/`, `proof/100-delta/`) were preserved untouched.

## D-004 — CONFLICT-001: canonical V197 hash — repository supersedes the plan, pending ratification

**Older requirement.** Masterplan §9.1 pins canonical V197 to
`252eee806ece31ef829a2dc5cd45aa8d8f8e855db1bde98b6f87193d786633c3`.

**Newer state.** The repository pins and gate-enforces
`d4f7f2d3e4c8e36dfc0c6edd51a028f28a04afbc2afa434a319009cb2f122bc6`.

**Evidence.** `git cat-file blob 03c9de12` (the canonical host at commit `6ce2c46`) hashes to
exactly the plan value. Commit `f8ddd7a` (2026-07-18 20:09:38 +0500, "Consolidate exact V197
star brain interface") replaced it using `apps/web/scripts/rebuild-v197-canonical.mjs`, which
extracts the Base64 Entry/Universe documents, prunes dead legacy styles/scripts via JSDOM, and
re-embeds them; size 1,029,176 → 718,041 bytes. `f8ddd7a` is an ancestor of HEAD.

**Winner.** The repository state, provisionally — the rebuild implements Masterplan §9.6
"Stage S — static-source extraction" (remove runtime duplicate copies and dead legacy
handlers), so it is the plan's own convergence path rather than a violation of it.

**Reason it is not closed.** Product law permits a new canonical source only on explicit
founder approval, and no such approval is recorded. Logged as blocker **B1**.

**Affected surfaces.** Entry stage, Universe stage, every V197 control.
**Affected tests.** `scripts/check-v197-integrity.ts`, `npm run v197:integrity`, all `v197-*.spec.ts`.
**Resolution status.** OPEN — awaiting founder ratification.

## D-005 — Two backend rate-limit failures: product sound, test system defective

> **Revised 2026-07-25 on founder direction.** The original entry closed this as "my own
> artifact" on the strength of a clean re-run. That was too generous. A clean re-run proves the
> product limiter works; it does not prove the test system is isolated. Corrected classification:
>
> ```
> PRODUCT DEFECT:              NO
> TEST-INFRASTRUCTURE DEFECT:  YES — RESOLVED, isolation proof passing
> ```
>
> The founder's reasoning stands on its own: if two test processes can flush the same Redis and
> drop the same database, the suite can silently invalidate itself at any time, and the next
> phantom failure might be read as a real defect — or a real defect might be dismissed as a
> phantom. Both directions are dangerous.

### Original diagnosis (retained)

First full backend run reported `2 failed, 178 passed`:
`test_login_rate_limited_after_burst` and `test_register_rate_limited_after_burst`.

Diagnosis performed rather than assumed:
- both tests pass in isolation (`2 passed in 3.42s`);
- `test_auth.py` alone passes (10/10);
- the seven test files that precede `test_auth.py` in collection order plus `test_auth.py`
  pass together (47/47);
- Redis was reachable throughout — key `rl:register:127.0.0.1` was present with a live TTL.

Root cause: a backgrounded pytest invocation was still running against the **same** Redis
database and test database while the foreground run executed. The `client` fixture calls
`flushdb()` per test, so the concurrent run's flush wiped the other run's limiter counters
mid-test, letting the eleventh request through. Re-running the suite alone gave
**`180 passed in 53.76s`**.

Conclusion: the prior audit claim "180 backend tests passed" is **VERIFIED**. The rate
limiter itself is sound. The incident is recorded so it is never mistaken for a defect, and
because it shows the suite is not safe to run concurrently against a shared Redis.


### Isolation fix

Two shared resources were fixed-name, so any second invocation collided with the first:

| Resource | Before | After |
| --- | --- | --- |
| test database | `nur_test` — both runs `DROP DATABASE … WITH (FORCE)` then recreate | `nur_test_<run_id>` |
| Redis keyspace | db 0, wiped by `flushdb()` per test | keys prefixed `nurtest:<run_id>:`, cleared by scan-and-delete over that prefix only |
| project object root | one shared directory | per-run directory |
| `nur_admin` / `nur_app` roles | genuinely cluster-wide; concurrent `ALTER ROLE` raced with `ERROR: tuple concurrently updated` | provisioned under `pg_advisory_lock('nur_test_role_provisioning')` held for one psql session, with each `CREATE ROLE` tolerating `duplicate_object` |

Implementation:

- `app/core/config.py` — new `redis_key_namespace` setting (`NUR_REDIS_KEY_NAMESPACE`), empty in
  production where the instance is not shared.
- `app/services/rate_limit.py` — every key now passes through `namespaced()`. This is the only
  product-code change, and it is the mechanism the founder named ("unique Redis namespace per
  test run"); it also makes one Redis safely shareable across environments.
- `app/tests/conftest.py` — per-run id (`NUR_TEST_RUN_ID`, else a random 12-hex), per-run
  database and namespace, `clear_run_keys()` replacing `flushdb()`, advisory-locked role
  provisioning, and session teardown that drops both the database and the namespace.
- `app/tests/test_bounded_load.py` — its recovery step also called `flushdb()`. Found by the new
  guard test, not by inspection. Now calls `clear_run_keys()`.

### Regression proof

`app/tests/test_run_isolation.py` — 7 tests:

1. shared resource names are per-run, and the database is never the fixed `nur_test`;
2. limiter keys carry the run namespace;
3. a foreign run's cleanup deletes exactly its own key and leaves this run's counter intact;
4. **a foreign run exhausting the same logical bucket, then tearing down, does not reopen this
   run's closed rate-limit window** — the precise corruption that caused the phantom failures;
5. `conftest.py` contains no `flushdb` call;
6/7. no `.flushdb(` or `.flushall(` call anywhere in the suite (parametrised).

The guard matches the call form `.flushdb(`, not the bare word, so prose describing the hazard
is allowed while a real call fails the build.

### Evidence

| Run | Result |
| --- | --- |
| single suite | 187 passed |
| **three concurrent suites (A/B/C)** | **187 passed each, exit 0 each, 57.97s / 58.01s / 58.01s** |
| before the fix, two concurrent suites | one run 187 passed; the other **187 errors in 3.81s** (`ERROR: tuple concurrently updated`) |
| leftover databases after runs | none |
| leftover Redis keys after runs | none |
| `ruff check .` | All checks passed |

Test count rose 180 → 187: the seven isolation regression tests. No existing test was weakened,
skipped, or forced serial — the founder explicitly forbade hiding this by serialising CI.

## D-006 — Ephemeral Redis started for the test run

Redis/Valkey was not running. Started `valkey-server` on port 6379 with its data directory
inside the session scratchpad. No product configuration changed. This is a local test
dependency, not a repository modification.

## D-007 — Requirement matrix granularity

229 requirement rows across G00–G16. One row per substantive, independently verifiable
requirement — the level at which a gate can actually pass or fail. Rows carry the source
document and line range so any verdict can be traced back to the binding text.

## D-008 — Status vocabulary is deliberately harsher than "done / not done"

`BACKEND_ONLY` and `UI_ONLY` exist as first-class statuses because the orchestrator states
that neither is product-complete. Six requirements are currently `BACKEND_ONLY` — Personal
Memory, Teach NUR, Billing, account export, and related surfaces — and each is counted as
**not** passing, not as "mostly done".

## D-009 — FD-002: existing OpenAI key reused, rotation cancelled

Founder override. The key that produced `LIVE_TALK_PASS` is reused unchanged. Retrieved only
from live local configuration (`/home/nur/NUR-LIVE-TALK-PROOF-20260723/.env.local`, mode 600),
never from transcripts, reports, Git history, screenshots, or archived plaintext.

Two distinct active key values exist in local worktree configuration. I did **not** raise
`FOUNDER_ACTION_REQUIRED_IDENTIFY_EXISTING_OPENAI_KEY`, because the founder's own priority list
names source #1 explicitly and that source resolves to exactly one value — the choice is
determinate, not a guess. Provenance was confirmed independently: the live key line fingerprints
to the same value the forensic audit recorded for archive snapshot 06, the configuration that
produced `LIVE_TALK_PASS` at `33a5dab`. The unselected group is listed by path in FD-002.

`SAME_OPENAI_KEY=true`. Provisioned to `.env.local` mode 600, git-ignored, never displayed,
echoed, logged, committed, or written into any report or evidence file. Fingerprints exist only
in `/home/nur/NUR-V5-100-COMPLETION/.secret-evidence/` (dir 700, file 600).

Blocker B2 withdrawn; B3 closed. Residual risk stated plainly in FD-002: archive copies were
readable before quarantine, so quarantine limits further spread but cannot revoke access already
taken. That risk is now accepted by decision rather than by oversight.

## D-010 — Two failures during the live gate run were rate limiting, not defects

The first `G05_LIVE_AI` gate run failed with the universe stage never becoming visible, and
`G03_V197` lost 6 of 13 browser tests. Both looked like presentation defects.

Neither was. Every browser spec signs in as the same demo owner, and login is limited to 10
attempts per 300 seconds per ip+email. I had just run the UI smoke eleven times while de-flaking
it, then two browser gates back to back. The window was exhausted, sign-in returned 429, and the
authenticated shell never rendered.

Proof: after waiting out the 300-second window with no code change, the two-turn proof returned
`LIVE_TALK_PASS` with both turns exact-matched and both persisted through reload, and the formal
`G05_LIVE_AI` gate ran `live_two_turn_proof` at exit 0.

This is the second time in this mission that shared-resource contention produced failures that
mimicked product defects — the first was the concurrent-pytest Redis flush (D-005). Same lesson:
a red result is not evidence until the environment is ruled out.

Fix: `browser_gate` now honours `NUR_GATE_BROWSER_SPACING_SECONDS`, which spaces consecutive
browser gates. Default 0 for single-gate runs; set it to 310 for `ALL`. The production limit was
not raised and no spec was weakened — the constraint is real and the runner respects it.

Still open: `G03_V197` must be re-run with spacing before its 6 failures can be called real. They
are currently **indeterminate**, not confirmed defects.
