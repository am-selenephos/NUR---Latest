# GIT HISTORY & LANE RECONCILIATION — Phase 4

Machine table: GIT_LANE_RECONCILIATION.csv. All 13 git bundles verify OK
(`git bundle verify`); 2 lane tarballs pass `gzip -t`.

## Bundle inventory (verified)
| Bundle | Heads | Verify |
|---|---|---|
| git-bundles/01-NUR-INTEGRATION | 14 | OK |
| git-bundles/02-NUR-WT-BACKEND | 14 | OK |
| git-bundles/03-NUR-G10-G15 | 19 | OK |
| git-bundles/04-NUR-FABLE-ROOT | 14 | OK |
| git-bundles/05-NUR-FABLE-CONTROL-MATRIX | 14 | OK |
| git-bundles/06-NUR-LIVE-TALK-PROOF | 14 | OK |
| git-bundles/07-NUR-DEMO-TALK-FIXED | 14 | OK |
| git-bundles/08-NUR-DEMO-COUSIN | 14 | OK |
| existing-bundles/NUR-BACKEND-BEFORE-20260729 | 1 | OK |
| existing-bundles/NUR-BEFORE-FABLE-20260720-forensic-rebuild | 8 | OK |
| existing-bundles/NUR-FINAL-READINESS-1bd55de | 1 | OK |
| existing-bundles/NUR-LANE-A-20260730 | 1 | OK |
| existing-bundles/NUR-LANE-B-20260730 | 1 | OK |

## Ancestry vs current HEAD 6d7eeef
| Lane | HEAD | Ancestor of 6d7eeef? | +integrated | in-lane-not-in-HEAD |
|---|---|---|---|---|
| 01 integration | 7a56510 | YES | 1 | 0 |
| 02 Lane A backend | 4525110 | YES | 36 | 0 |
| 03 Lane B G10-G15 | 4ded46c | **NO** | 45 | 4 |
| 04 Fable root | 69d1d70 | YES | 45 | 0 |
| 05 Control matrix | 3102b48 | YES | 8 | 0 |
| 06 Live-Talk | 33a5dab | YES | 12 | 0 |
| 07 Demo Talk fixed | 1682abc | YES | 19 | 0 |
| 08 Demo cousin | 28f23e5 | YES | 22 | 0 |

## The one non-ancestor lane: Lane B (03)
Lane B tip `4ded46c` is NOT in HEAD's commit ancestry (merge-base 69d1d70, 4
commits ahead). Its 4 tip commits were **content-integrated by reimplementation**,
not git-merge:

| Lane B commit | → Integration commit (in current history) | Feature |
|---|---|---|
| 7461b98 feat(systems): complete audited seven-system returns | dfa20bd feat(systems): integrate persisted Seven Systems | Seven Systems |
| ad84e95 feat(i18n): complete scoped translation contract | 28f23e5 feat(i18n): integrate translation and RTL contract | Translation/RTL |
| d58a736 feat(community): complete bounded social moderation backend | 72c747c feat(community): integrate social and moderation domain | Community/moderation |
| 4ded46c wip(rescue): preserve incomplete G13 group research work | 85883b1 feat(research): integrate Group NUR and evidence research | Group research |

Content presence in current Git confirmed: 12 i18n/translation files, 18
community/council/consultation files, 11 living/systems files, and migrations
0027_translation_contract / 0028_community_moderation / 0029_group_research
(byte-identical to Lane B's 0022/0023/0024 except revision-id lines).

## Migration renumbering (integration hygiene)
Lane A occupied migration slots 0022–0026 (password_recovery, personal_memory_spine,
teach_nur_pipeline, billing_revenue_spine, glow_progression_spine). Lane B's
translation/community/group-research migrations were renumbered to 0027–0029 to
sit after Lane A. Single Alembic head verified: **0030_project_execution_storage**
(Phase 0). No lost migration, no divergent head.

## Lost files / altered contracts
None found. Every current tracked file is byte-present in the archive
(PATH_VERSION_MATRIX). The only modern paths absent from current Git are the 3
renumbered (present) migrations and the intentionally-removed build-week-gate.sh.
