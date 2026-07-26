# Final GitHub publication report

Reconciliation of the NUR UI / Systems / TRIBE mission into the real repository.

| | |
| --- | --- |
| Repository | `/home/nur/NUR-INTEGRATION-20260722` |
| Remote | `https://github.com/am-selenephos/NUR.git` |
| Base branch | `main` |
| Integration branch | `integration/nur-ui-reconcile-20260726` |
| Starting HEAD | `902c31b` |
| Final HEAD | `ad01267` |
| Commits | 4 |
| Draft PR | [#7](https://github.com/am-selenephos/NUR/pull/7) |

Remote and local both resolve to `ad0126784869de0c4e024c1586e485c7c83f30e40`.

## Commits

```
ad01267  docs: reconciliation inventory, UI audit and mission evidence
7ee33b5  test: guard the star paint, deep field, CPU budget and UI census
d6a9d1b  feat(v197): stellar star paint, parallax deep field and control corrections
905ad87  feat(systems): reduce the Star Systems to six and remap owner data
```

127 files changed, 23,875 insertions, 284 deletions. 16 MB of that is curated
screenshot evidence.

## Dispositions

From `ALL_NUR_WORK_INVENTORY.csv` — 63 items, every one with a final disposition:

| Action | Count |
| --- | --- |
| INTEGRATE | 43 |
| KEEP_AS_EVIDENCE (left untracked) | 12 |
| REWRITE_TO_FIT | 2 |
| REJECT_SECRET | 2 |
| REJECT_OBSOLETE | 2 |
| REJECT_LARGE_BINARY | 1 |
| ARCHIVE_OUTSIDE_REPO | 1 |

Deliberately excluded: `.venv-tribe` (8.2 GB), `NUR-QUARANTINE-SECRETS` (585 MB
of archives holding historical keys), `.secret-evidence/`, reference videos, and
114 MB of earlier missions' screenshots — metrics committed, images not.

## Verification

| Check | Result |
| --- | --- |
| Backend tests | 187/187 |
| Frontend unit | 65/65 |
| Typecheck | 0 errors |
| Build | 338.86 kB (87.90 kB gzip) |
| V197 integrity | `"pass": true` |
| Ruff | clean |
| Canonical V197 SHA-256 | `d4f7f2d3…f2122bc6` — unchanged |
| Migration | applied and reversed on a clean chain and on the runtime database |
| Live Talk | PASS (gpt-4.1, persisted, visible after refresh) |
| Fresh checkout | builds identically from `ad01267` |
| CPU (CDP task time) | Entry 75.2%, Systems 17.4% (baseline 19.1%) |
| Secrets in staged content | none |

## Pre-existing failures, attributed rather than inherited

- `e2e/auth.spec.ts` waits for `tab-register`, a test id present nowhere in
  canonical V197. The file is untouched by this branch.
- `e2e/track-a-mobile-webkit.spec.ts` fails identically with this branch's
  `apps/web/src` stashed, proving it is not a regression.

## Open items

- **P0** — six Universe lenses render effectively the same page: identical
  control and card counts, under 2% text difference. The largest open design
  defect; measured in `docs/v9/NUR_COMPLETE_UI_AUDIT.md`.
- **P1** — 62 of 92 controls under 44×44. WCAG 2.2 requires 24×24 with a spacing
  exception, which has not been measured, so no conformance claim is made.
- Reference videos absent, so no shot ledger exists.
- TRIBE blocked on gated `meta-llama/Llama-3.2-3B`.

## Rollback

```bash
git checkout main     # the branch is isolated; nothing was merged
```

Canonical V197 is byte-identical to `main`, so no presentation rollback is
required. Nothing was force-pushed, no history rewritten, no remote branch
deleted, and the OpenAI key was neither rotated nor exposed.
