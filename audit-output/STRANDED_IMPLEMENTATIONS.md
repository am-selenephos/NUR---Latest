# STRANDED IMPLEMENTATIONS — Phase 3

Definition: a distinct implementation present in one or more archived snapshots that
is **not byte-present in current Git**. Computed from PATH_VERSION_MATRIX.csv
(223 archive-only logical paths) then filtered to code/migrations/scripts.

## Result: NO production feature is stranded.

Every archive-only path resolves to one of: renumbered-but-present migration,
intentionally-removed release-gate script, superseded prior generation, or test
evidence (screenshots/proof). Details:

### A. Renumbered migrations — feature PRESENT, sequence changed (NOT stranded)
| Lane B source (snapshot 03) | Current Git equivalent | Non-revision-line diff | Disposition |
|---|---|---|---|
| alembic 0022_translation_contract.py | 0027_translation_contract.py | 2 lines (revision ids only) | PORTED (renumbered after Lane A 0022-0026) |
| alembic 0023_community_moderation.py | 0028_community_moderation.py | 2 lines (revision ids only) | PORTED |
| alembic 0024_group_research.py | 0029_group_research.py | 2 lines (revision ids only) | PORTED |

Regression risk: NONE. Feature tables + models present; single Alembic head
(0030) verified in Phase 0. Required test: `alembic upgrade head` on a clean DB
(run in Phase 6).

### B. Intentionally removed (NOT stranded)
| Path | Present in | Removed by | Disposition |
|---|---|---|---|
| infra/scripts/build-week-gate.sh | 02,03,04,07,08 | commit e2b0611 "chore(release): clean public naming" | REJECT (Build-Week submission gate; out of product scope) |

### C. Superseded prior generations (NOT stranded — archive/design-reference)
| Source | Nature | Disposition |
|---|---|---|
| snapshot 09-NUR-OLDER-LOCAL (110 files: api/, Vue app, 3 sqlite) | Entirely different product (mental-health chatbot: ConversationState/SafetyLane/Mood/AgeMode/trusted_contacts/waitlist). `api/app/routes/api.py`, `App.vue`, `useNurStore.ts`, design-reference galaxy HTML | ARCHIVE (DESIGN_REFERENCE). Do not port. |
| snapshot 10-NUR-DOWNLOADS-SOURCE (React `src/routes/*.tsx`, `src/lib/api.ts`, `v197-universe*.css`, galaxy `engine.js`) | Pre-lane React/TSX generation of the current product, before the canonical single-file V197 bridge architecture | ARCHIVE. The current V197 is the intentional immutable presentation; the React route components are the REJECTED earlier skin. Do not port. |
| Older bridge/service versions (v197Adjuncts.ts 83–90KB, glow_service.py 53KB, etc. in 02/03) | Earlier lane versions of files integrated & improved in baseline | SUPERSEDED. Current integration is newer. |

### D. Test evidence (NOT code)
61 screenshots + 4 proof JSON in modern snapshots (proof/… dirs) that were not
committed to current Git. Disposition: TEST_EVIDENCE — retained in archive, not
release artifacts.

## Backend implementation-generation ranking (behavioral, not mtime)
For files present in multiple snapshots, the **current integration baseline (01) +
Live-Talk (06)** is the newest/most-capable in every case examined:
- `openai_provider.py`: baseline has full `_classify_provider_exception`
  (quota/ratelimit/unsupported-model/timeout mapping); Lane B (03) has a simpler
  `_is_auth/_is_retryable`; snapshot 10 has NO streaming. **Current 6d7eeef adds
  the gpt-4.1 `reasoning.effort` gate on top of baseline** — strictly newest.
- `prompts.py`: baseline has the full safety-rule block; current 6d7eeef adds the
  verbatim `kind:id` citation contract + empty-evidence rule — strictly newest.
- `intelligence_kernel.py` / `streaming.py` / `verifier.py`: baseline is
  fail-closed with `TalkProviderFailure`/`talk.failed`, safety-gated verifier
  (persona/dependency/injection flags); Lane B (03) and snapshot 10 are older
  (no fail-closed error event, no safety flags). Current is newest.
