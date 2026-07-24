# G03_V197 — BLOCKED_EXTERNAL

- commit: `9a88eedea3fac406a0410b54ef4d99aafd4cc341`
- branch: `completion/nur-v5-full-pass`
- environment: `local`
- window: 2026-07-24T22:56:01Z → 2026-07-24T22:56:02Z
- dirty entries: 9

## Notes

API not reachable at http://localhost:8000/healthz — start the stack: bash RUN_NUR.sh

## Steps

| step | exit | seconds | log |
| --- | --- | --- | --- |
| v197_integrity
 | 0 | 0 | `v197_integrity.log
` |
| control_matrix_regen
 | 0 | 0 | `control_matrix_regen.log
` |
| control_matrix_fresh
 | 0 | 0 | `control_matrix_fresh.log
` |
| no_broken_controls
 | 0 | 0 | `no_broken_controls.log
` |
| browser_suite
 | skipped | — | API stack not running
 |
| deferred_controls
 | skipped | — | 7 controls remain NOT_IMPLEMENTED_VISIBLE (G03-007)
 |
| backend_only_surfaces
 | skipped | — | Personal Memory, Teach NUR and Billing unreachable from V197 (G03-008..010)
 |
