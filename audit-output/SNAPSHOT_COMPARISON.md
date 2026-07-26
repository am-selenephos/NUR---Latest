# SNAPSHOT COMPARISON — Phase 3

10 snapshots, 693 distinct logical paths, 885 unique repo content hashes.
Full per-path/per-snapshot hash matrix: PATH_VERSION_MATRIX.csv.

## Logical-path verdicts (693 paths)
| Verdict | Count | Meaning |
|---|---|---|
| IDENTICAL_EVERYWHERE | 354 | Same content in every snapshot that has it AND in current Git |
| CURRENT_MATCHES_SOME_ARCHIVE | 116 | Current Git file matches ≥1 snapshot version (differs from others) |
| ARCHIVE_ONLY_NOT_IN_CURRENT | 223 | In archive, not byte-present in current Git (see breakdown) |

All 470 current tracked files fall in the first two rows — i.e. **every current
file is byte-present in the archive.** Zero current files differ from all archive
versions.

## The 10 snapshots — identity and generation
| # | Snapshot | HEAD | Generation | Relationship to current 6d7eeef |
|---|---|---|---|---|
| 01 | NUR-INTEGRATION | 7a56510 | **Unified integration baseline** | Direct parent (HEAD = 01 + 1 Live-Talk commit) |
| 02 | NUR-WT-BACKEND | 4525110 | Lane A backend (billing/intelligence/teach-nur/memory/projects) | Ancestor; +36 integrated |
| 03 | NUR-G10-G15 | 4ded46c | Lane B (systems/i18n/community/group-research) | Content-integrated (not ancestor); migrations renumbered |
| 04 | NUR-FABLE-ROOT | 69d1d70 | Fable final-readiness (canonical V197 frontend) | Ancestor; +45 |
| 05 | NUR-FABLE-CONTROL-MATRIX | 3102b48 | V197 control-matrix hardening | Ancestor; +8 |
| 06 | NUR-LIVE-TALK-PROOF | 33a5dab+wt | Live-Talk proof working tree | 6 files == current HEAD (proven) |
| 07 | NUR-DEMO-TALK-FIXED | 1682abc | Demo Talk persistence fix | Ancestor; +19 |
| 08 | NUR-DEMO-COUSIN | 28f23e5 | Cousin demo | Ancestor; +22 |
| 09 | NUR-OLDER-LOCAL | (working) | **Different product** (mental-health chatbot; api/, Vue, SQLite) | SUPERSEDED — design reference only |
| 10 | NUR-DOWNLOADS-SOURCE | (working) | Pre-lane React/TSX generation of current product | SUPERSEDED |

## Architectural generations (do not conflate)
1. **Generation 0 (snapshot 09):** A separate mental-health companion product —
   crisis/safety lanes, mood, age modes, trusted contacts, waitlist, galaxy events,
   SQLite persistence, Vue frontend. Shares only the "NUR" name and galaxy motif.
   Entirely replaced. Its 3 `.sqlite3` files are old test fixtures (no secrets/PII).
2. **Generation 1 (snapshot 10):** The current product's early form — FastAPI +
   Postgres + React/TSX routes (`CapsuleRoom.tsx`, `Systems.tsx`, `UniverseLenses.tsx`),
   `src/lib/api.ts`, a multi-file `v197-universe*.css` skin, and a non-streaming
   Talk kernel. This is the **rejected earlier React skin** — superseded by the
   canonical single-file V197 (`NUR_V197_CHECKBOX_TICK_RESTORED.html` + bridge).
3. **Generation 2 (snapshots 01–08 + current):** Canonical V197 presentation
   (immutable HTML + `src/bridge/v197*.ts`) over the unified FastAPI/Postgres/Celery
   backend. Lanes A and B are complementary halves; snapshots 04–08 layer the
   frontend, demo, and Live-Talk work; snapshot 01 is their integration; current
   6d7eeef is 01 + the Live-Talk gpt-4.1 fix.

## Intentional immutable V197 vs. obsolete React UI
- **Keep (canonical):** `apps/web/public/v197/NUR_V197_CHECKBOX_TICK_RESTORED.html`
  and `apps/web/src/bridge/v197*.ts` (present & identical across 01/04/05/06/…).
- **Reject (obsolete):** snapshot 10's `apps/web/src/routes/**/*.tsx`, `src/lib/api.ts`,
  `src/styles/v197-universe*.css`, `src/galaxy/engine.js`. These are Generation-1
  React and are NOT in current Git by design.
