# READ COVERAGE — Phase 2

Reconciliation of every one of the 3,964 archived file paths. FILE_LEDGER.csv has
exactly one row per path (3,964 data rows == 3,964 archive paths == ALL_PATHS.txt).

## Totals
| Metric | Count |
|---|---|
| Total file paths | 3,964 |
| Paths successfully opened / hashed (independent) | 3,964 (100%) |
| Failures opening / hashing | 0 |
| Unique contents (by SHA-256) | 913 |
| — unique text contents | 791 |
| — unique binary contents | 122 |
| Duplicate paths (content == a canonical elsewhere) | 3,051 |

## Text handling (791 unique contents)
| Tranche | Count | How reviewed |
|---|---|---|
| Byte-identical to a current-Git tracked file | 454 | Reviewed in the live repo (`/home/nur/NUR-INTEGRATION-20260722`), incl. the prior Live-Talk session's line-level work on the 6 AI/Talk files |
| Historical-only unique text | 337 | Read from the archive (see below) |

Historical-only (337) review method — all concatenated into 44 header-delimited
review bundles + 20 oversized files handled individually:
- **Core backend (AI, cognition, DB models, provider, verifier, streaming, kernel):
  read completely** via bundles 02, 03, 04, 06 (openai_provider/prompts/schemas/
  intelligence_kernel/streaming/verifier/memory_service across snapshots 01/03/10;
  engagement/projects/community/cognition models across 02/03/09/10).
- **Routes / services / workers / “other” backend:** structurally reviewed
  (every FILE header + every class/def/route signature enumerated; representative
  bodies read). Bundles 05, 07–19, 33–38.
- **Frontend (old Vue app, downloads-source V197 CSS/bridge/lib, older bridge
  versions), tests, docs, old-arch:** reviewed as older/superseded generations
  (see SNAPSHOT_COMPARISON.md). Bundles 20–32, 39–44 + oversized CSS/bridge files.
- 1 oversized generated artifact (`04-.../chromium-performance-trace.json`, 32 MB)
  header-inspected only — a Chromium perf trace, GENERATED.

No text file was marked reviewed on the basis of `find`/`grep`/`sha256sum` alone.
Duplicates were each opened and hashed; their content equivalence to a reviewed
canonical is proven by SHA-256, not assumed by filename.

## Binary handling (122 unique contents)
| Type | Unique | Disposition | Inspection |
|---|---|---|---|
| Git bundles (.bundle) | 13 | TEST_EVIDENCE | `git bundle verify` — all 13 OK; heads/commits enumerated (Phase 4) |
| Lane worktree tarballs (.tar.gz) | 2 | TEST_EVIDENCE | `gzip -t` OK; 777 + 699 entries listed |
| Screenshots (.png) | 94 | TEST_EVIDENCE | Visually inspected representative set (V197 landing, live-Talk two-turn, after-reload, settings) |
| Brand fonts (.woff2) | 4 | DESIGN_REFERENCE | Identified: Crimson Pro + Bodoni Moda (latin normal/italic) |
| SQLite DBs (.sqlite3) | 3 | RUNTIME_STATE | Read-only schema + row scan — old-product test fixtures; **no secrets, no email/PII** |
| Celery beat schedule (+shm/wal) | 6 | RUNTIME_STATE | Celery scheduler state; should be gitignored (see Security report) |

## Failures / unresolved
- Failures: **0**
- Unresolved (UNKNOWN_REQUIRES_REVIEW): **0**

Every path is opened, hashed, classified, and dispositioned. Coverage is complete.
