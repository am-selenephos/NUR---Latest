# 01 — ARCHIVE INTEGRITY & EXTRACTION

## Archive
- File: `/home/nur/Downloads/NUR-TRUE-FULL-AUDIT-20260801-144301.tar.zst`
- Size: 204,434,534 bytes (compressed); 278,620,160 bytes decompressed stream
- Expected SHA-256: `d46a5d92493caa55421cfeaba93b65e40171f0e60b1392cb1a0b92bb22b6ac9c`
- Computed SHA-256: `d46a5d92493caa55421cfeaba93b65e40171f0e60b1392cb1a0b92bb22b6ac9c`
- **SHA-256 MATCH: YES**
- `zstd -t` integrity: **PASS** (278620160 bytes, no corruption)

## Extraction
- Target (disposable): `/tmp/claude-1000/.../scratchpad/audit-extract/NUR-TRUE-FULL-AUDIT-STAGE`
- tar exit: 0
- Warnings: 3086 lines, ALL of type "time stamp ... in the future" (archive dated 2026-08-01; audit clock earlier). No content/corruption warnings. Harmless.
- No existing repository was overwritten (extracted to /tmp scratchpad only).

## Recalculated counts (independent, NOT trusting stated figures)
| Metric | Stated (prompt) | Archive SUMMARY | Independently recomputed | Match |
|---|---|---|---|---|
| Total files (repos+bundles+metadata) | ~3,964 | — | **3,964** | ✓ |
| Repo-file instances | 3,922 | 3,922 | **3,922** | ✓ |
| Unique repo content hashes | 885 | 885 | **885** | ✓ |
| Main snapshots/worktrees | 10 | 10 | **10** | ✓ |
| Unique hashes across ALL 3,964 | — | — | 913 (885 repo + 28 bundle/metadata-only) | n/a |

## Cross-check vs archive's own manifest
- Archive ships `metadata/ALL-FILE-SHA256.txt` (3,922 lines, repo files).
- My independent sha256sum of the same 3,922 files: **0 differences**. Manifest is accurate.

## Corpus layout (3,964 files)
| Group | Files | Notes |
|---|---|---|
| repos/ (10 snapshots) | 3,922 | working-tree copies incl. each `.git` gitdir-pointer file |
| git-bundles/ | 8 | audit-generated bundles 01–08 (one per live snapshot) |
| existing-bundles/ | 7 | pre-existing bundles + 2 lane worktree tarballs |
| metadata/ | 27 | per-snapshot .txt descriptors, index/working-tree patches, ALL-FILE-PATHS/SHA256, SUMMARY |

## Snapshots (repos/)
| # | Snapshot | Files |
|---|---|---|
| 01 | NUR-INTEGRATION-20260722 | 492 |
| 02 | NUR-WT-BACKEND | 430 |
| 03 | NUR-G10-G15 | 402 |
| 04 | NUR-FABLE-ROOT | 436 |
| 05 | NUR-FABLE-CONTROL-MATRIX | 481 |
| 06 | NUR-LIVE-TALK-PROOF | 465 |
| 07 | NUR-DEMO-TALK-FIXED | 452 |
| 08 | NUR-DEMO-COUSIN | 438 |
| 09 | NUR-OLDER-LOCAL | 110 |
| 10 | NUR-DOWNLOADS-SOURCE | 216 |

## Generated outputs
- `audit-output/ALL_PATHS.txt` — 3,964 paths (independent)
- `audit-output/ALL_SHA256.txt` — 3,964 sha256 lines (independent)

**Verdict: Archive integrity CONFIRMED. Safe to audit.**
