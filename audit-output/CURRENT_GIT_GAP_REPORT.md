# CURRENT GIT vs COMPLETE CORPUS — Phase 5 Gap Report

Machine table: CURRENT_GIT_FILE_VERDICT.csv (470 tracked files).

## Per-file verdict distribution
| Verdict | Count |
|---|---|
| UNCHANGED_FROM_BASELINE (identical to snapshot 01 / all snapshots) | 464 |
| BEST_AVAILABLE (Live-Talk proven, newer than baseline) | 5 |
| NEW_CURRENT (added by Live-Talk commit) | 1 |
| OLDER_THAN_ARCHIVE / CONFLICTING / MISSING_ARCHIVED_FEATURE | 0 |

Current Git = integration baseline `7a56510` for 464 files + Live-Talk `6d7eeef`
for 6 files (5 modified + 1 new). **No current file is older than or conflicts
with any archived version.**

## What current Git contains
The unified Generation-2 product: FastAPI/Postgres/Celery backend with all of
Lane A (auth, password recovery, Talk streaming, memory candidates, personal
memory, Teach NUR, intelligence/Omega, billing, glow, projects, notifications,
capsules) and Lane B (Seven Systems, translation/RTL, community/moderation, group
research/consultations), plus the canonical V197 frontend bridge, demo seeds, and
the Live-Talk gpt-4.1 provider fix. 470 tracked files, 30 migrations (single head
0030), one branch `release/nur-p0-candidate`, tag `nur-p0-rc1` at HEAD.

## What is missing
Nothing release-blocking. The only archived modern paths absent from current Git:
1. **3 Lane B migrations renumbered, not lost** — features + tables present under
   0027/0028/0029.
2. **build-week-gate.sh** — intentionally removed (release cleanup, commit e2b0611).

## What is newer elsewhere
Nothing. For every file present in both, current Git ties or leads. The Live-Talk
6 files are the newest versions in the entire corpus (snapshot 06 == current).

## What was accidentally omitted
Nothing detected. All 470 current files trace to the archive; all archived modern
code traces to current (renumbered/renamed where noted).

## What is intentionally excluded
- Generation-0 (snapshot 09) mental-health chatbot — different product.
- Generation-1 (snapshot 10) React/TSX skin — rejected in favor of canonical V197.
- `build-week-gate.sh`, internal construction docs, proof screenshots — release hygiene.
- `.env*` secrets (never tracked; `.env.example` only).

## What must be ported
Nothing. Integration is complete.

## What must not be ported
- Snapshot 09/10 code (superseded generations).
- Any archived `.env` / secret material.
- The unconditional `reasoning.effort` payload from baseline `openai_provider.py`
  (already fixed in 6d7eeef — porting backward would reintroduce the gpt-4.1 400).

## Release-blocking gaps
None from the corpus comparison. (Runtime/live-gate status determined in Phase 6.)

## Documentation-only drift
`docs/FABLE_EXECUTION_LEDGER.md` references the removed `build-week-gate.sh`;
harmless historical reference.
